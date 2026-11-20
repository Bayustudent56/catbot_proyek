"""CatBot - mesin intent berbasis JSON (rule-based, tanpa model ML).

Alur pencocokan:
  1. Deteksi kata kunci darurat (urgent_keywords)  -> langsung intent `darurat_kesehatan`.
  2. Normalisasi teks: huruf kecil, buang tanda baca, koreksi typo ringan (difflib),
     lepas akhiran -nya.
  3. Skoring tiap pola:
       - frasa pola muncul utuh di pesan      -> skor dasar 1.0
       - selain itu: overlap token berbobot IDF (kata umum seperti "kucing" berbobot kecil),
         atau - bila >= 2 kata cocok - seberapa besar pesan tercakup pola (maks 0.85)
       - skor akhir = dasar x (0.6 + 0.4 x cakupan pesan), agar sapaan di dalam
         kalimat panjang tidak mengalahkan intent yang lebih relevan.
  4. Intent dengan skor tertinggi dipilih. Jika < threshold -> `fallback`.
"""
from __future__ import annotations

import difflib
import json
import math
import random
import re
from functools import lru_cache
from pathlib import Path

STOPWORDS = frozenset(
    "yang di ke dari dan untuk dalam itu ini si saya aku ku mau ingin tolong dong ya deh sih kah kok "
    "dengan pada agar supaya adalah sebaiknya nih".split()
)

# Kata tanya tidak membawa topik, jadi tidak dipakai untuk menilai kemiripan jawaban
QUESTION_WORDS = frozenset("apa apakah kenapa mengapa bagaimana gimana cara boleh harus perlu".split())

# Kamus sinonim kecil: frasa di pertanyaan -> kata yang dipakai di jawaban.
# Contoh: "tidak boleh" di pertanyaan, tetapi jawabannya memakai "dihindari".
# Bisa ditambah lewat kunci "synonyms" di akar intents.json (format sama).
DEFAULT_SYNONYMS = {
    "tidak boleh": ["hindari", "dihindari", "wajib"],
    "dilarang": ["hindari", "dihindari", "wajib"],
    "pantangan": ["hindari", "dihindari", "wajib"],
    "larangan": ["hindari", "dihindari", "wajib"],
    "jangan": ["hindari", "dihindari"],
    "berbahaya": ["hindari", "dihindari", "wajib"],
    "beracun": ["hindari", "dihindari", "wajib"],
    "racun": ["hindari", "dihindari", "wajib"],
    "berapa banyak": ["kebutuhan", "jumlah", "takaran", "porsi"],
    "berapa kali": ["kali", "sehari", "sekali"],
    "sering": ["sekali", "kali", "setiap", "umumnya", "rutin"],
}

FALLBACK_TAG = "fallback"
URGENT_TAG = "darurat_kesehatan"
DEFAULT_PET_NAME = "si meong"


def _tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split()


_PREFIXES = ("meng", "meny", "mem", "men", "me", "peng", "pem", "pen", "pe", "per", "ber", "ter", "di", "ke", "se")
_SUFFIXES = ("kannya", "annya", "kan", "an", "nya", "lah", "kah", "ku", "mu")
# Kata yang ada di hampir semua jawaban: tidak membantu membedakan jawaban
GENERIC_WORDS = frozenset({"kucing", "meong"})


# Peluluhan huruf awal: memotong -> potong, menulis -> tulis, mengirim -> kirim, menyisir -> sisir
_ASSIMILATION = {"mem": "p", "pem": "p", "men": "t", "pen": "t", "meng": "k", "peng": "k", "meny": "s", "peny": "s"}
_MIN_STEM = 5


@lru_cache(maxsize=4096)
def _stems(token: str) -> frozenset[str]:
    """Semua kemungkinan bentuk dasar (potong awalan/akhiran, minimal 5 huruf).
    Contoh: dimandikan & memandikan -> mandi; kepanasan -> panas; makanan -> makan."""
    out = {token}
    bases = [token]
    for pre in _PREFIXES:
        if token.startswith(pre):
            bases.append(token[len(pre):])
            if pre in _ASSIMILATION:
                bases.append(_ASSIMILATION[pre] + token[len(pre):])
    for base in bases:
        for suf in ("",) + tuple(x for x in _SUFFIXES if base.endswith(x)):
            stem = base[: len(base) - len(suf)] if suf else base
            if len(stem) >= _MIN_STEM:
                out.add(stem)
    return frozenset(out)


def _tokens_match(a: str, b: str) -> bool:
    return a == b or not _stems(a).isdisjoint(_stems(b))


class ChatbotEngine:
    def __init__(self, intents_path: str | Path):
        data = json.loads(Path(intents_path).read_text(encoding="utf-8"))
        self.threshold: float = float(data.get("threshold", 0.45))
        self.disclaimer: str = data.get("disclaimer", "")
        self.quick_replies: list[dict] = [
            qr for qr in (self._normalize_quick_reply(q) for q in data.get("quick_replies", [])) if qr
        ]
        self.urgent_keywords: list[str] = [
            " ".join(_tokens(k)) for k in data.get("urgent_keywords", []) if k.strip()
        ]
        self.intents: dict[str, dict] = {i["tag"]: i for i in data["intents"]}
        self.synonyms: dict[str, list[str]] = {
            " ".join(_tokens(k)): [" ".join(_tokens(v)) for v in vals]
            for k, vals in {**DEFAULT_SYNONYMS, **(data.get("synonyms") or {})}.items()
        }

        self._entries: list[tuple[str, str, list[str]]] = []  # (tag, frasa, token inti)
        df: dict[str, set[str]] = {}
        for intent in data["intents"]:
            for pattern in intent.get("patterns", []):
                full = _tokens(pattern)
                if not full:
                    continue
                core = list(dict.fromkeys(t for t in full if t not in STOPWORDS)) or full
                self._entries.append((intent["tag"], " ".join(full), core))
                for tok in core:
                    df.setdefault(tok, set()).add(intent["tag"])
        self._df = df
        self._vocab = sorted(df)
        self._n_intents = max(len(self.intents), 1)
        self._resp_meta = {tag: self._index_responses(i.get("responses") or []) for tag, i in self.intents.items()}

    # ------------------------------------------------------------------ util
    @staticmethod
    def _index_responses(responses: list[str]) -> dict:
        """Siapkan data untuk memilih respons yang paling sesuai dengan pertanyaan.

        - bases   : respons "inti". Respons yang hanya = respons inti + kalimat tambahan
                    dianggap varian, dan respons identik dihitung sekali.
        - tokens  : kata penting tiap respons (tanpa stopword & kata tanya).
        - weight  : bobot kata = seberapa khas kata itu di antara respons inti
                    (kata yang ada di semua respons inti berbobot 0).
        """
        bases: list[int] = []
        for i, text in enumerate(responses):
            if any(text == responses[j] or text.startswith(responses[j]) for j in bases):
                continue
            bases.append(i)

        def content_seq(text: str) -> list[str]:
            text = text.replace("{nama_kucing}", " ")
            return [t for t in _tokens(text)
                    if len(t) > 1 and t not in STOPWORDS and t not in QUESTION_WORDS and t not in GENERIC_WORDS]

        seqs = [content_seq(r) for r in responses]
        tokens = [set(seq) for seq in seqs]
        df: dict[str, int] = {}
        for i in bases:
            for t in tokens[i]:
                df[t] = df.get(t, 0) + 1
        n_base = max(len(bases), 1)
        return {"bases": bases, "tokens": tokens, "seqs": seqs, "df": df, "n_base": n_base}

    @staticmethod
    def _normalize_quick_reply(item) -> dict | None:
        """Terima 'teks biasa' atau {"label": ..., "message": ...}; hasil selalu {label, message}."""
        if isinstance(item, str):
            message = item.strip()
            label = message
        elif isinstance(item, dict):
            message = str(item.get("message") or item.get("label") or "").strip()
            label = str(item.get("label") or message).strip()
        else:
            return None
        return {"label": label, "message": message} if message else None

    def _idf(self, token: str) -> float:
        return math.log((self._n_intents + 1) / (len(self._df.get(token, ())) + 1)) + 1.0

    def _normalize(self, message: str) -> list[str]:
        out: list[str] = []
        for tok in _tokens(message):
            if tok in self._df or tok in STOPWORDS:
                out.append(tok)
            elif tok.endswith("nya") and len(tok) > 5 and tok[:-3] in self._df:
                out.append(tok[:-3])
            elif len(tok) >= 4:
                close = difflib.get_close_matches(tok, self._vocab, n=1, cutoff=0.84)
                out.append(close[0] if close else tok)
            else:
                out.append(tok)
        return out

    # --------------------------------------------------------------- publik
    def is_urgent(self, message: str) -> bool:
        variants = (_tokens(message), self._normalize(message))
        for toks in variants:
            text = f" {' '.join(toks)} "
            if any(f" {kw} " in text for kw in self.urgent_keywords):
                return True
        return False

    def match(self, message: str) -> tuple[str | None, float]:
        """Kembalikan (tag, skor). tag=None bila di bawah threshold / tidak ada kecocokan."""
        tokens = self._normalize(message)
        if not tokens:
            return None, 0.0
        text = f" {' '.join(tokens)} "
        msg_core = [t for t in tokens if t not in STOPWORDS] or tokens
        msg_set = set(msg_core)

        best: dict[str, tuple[float, int, int]] = {}
        for tag, phrase, core in self._entries:
            exact = f" {phrase} " in text
            if exact:
                base, matched = 1.0, set(core)
            else:
                matched = {t for t in core if t in msg_set}
                if not matched:
                    continue
                base = sum(self._idf(t) for t in matched) / sum(self._idf(t) for t in core)
                # Pesan pendek yang hampir seluruhnya tercakup pola panjang (kata asing menurunkan skor)
                if len(matched) >= 2:
                    msg_cov = sum(self._idf(t) for t in matched) / sum(self._idf(t) for t in msg_set)
                    base = max(base, 0.85 * msg_cov)
            coverage = len(matched & msg_set) / len(msg_set)
            score = base * (0.6 + 0.4 * coverage)
            # Seri: frasa utuh -> pola terpanjang (lebih spesifik); sebagian -> pola terpendek (paling pas)
            rank = (score, len(matched), len(core) if exact else -len(core))
            if tag not in best or rank > best[tag]:
                best[tag] = rank

        if not best:
            return None, 0.0
        tag, rank = max(best.items(), key=lambda kv: kv[1])
        score = round(rank[0], 3)
        return (tag, score) if score >= self.threshold else (None, score)

    def respond(self, message: str, cat=None) -> dict:
        message = (message or "").strip()
        if not message:
            return self._build(FALLBACK_TAG, 0.0, False, cat, message)
        if self.is_urgent(message):  # prioritas tertinggi; tampilkan SEMUA langkah darurat
            return self._build(URGENT_TAG, 1.0, True, cat, message, show_all=True)
        tag, score = self.match(message)
        return self._build(tag or FALLBACK_TAG, score, False, cat, message)

    def welcome(self, cat=None, user_name: str | None = None) -> str:
        if cat is not None:
            who = f"Hai, {user_name}! " if user_name else "Hai! "
            return (f"{who}Senang bertemu denganmu dan {cat.name}. "
                    f"Ada yang ingin kamu tanyakan tentang perawatan {cat.name} hari ini?")
        return "Hai! Aku CatBot 🐱 Tanyakan apa saja seputar pakan, perawatan, dan perilaku kucing."

    # -------------------------------------------------------------- privat
    def _keyword_pick(self, intent: dict, message: str) -> int | None:
        """Pilih respons ke-i yang daftar response_keywords[i]-nya paling banyak cocok."""
        groups = intent.get("response_keywords") or []
        if not groups:
            return None
        text = " ".join(_tokens(message))
        normalized = " ".join(self._normalize(message))
        scores = []
        for i in range(len(intent.get("responses") or [])):
            kws = groups[i] if i < len(groups) else []
            hits = 0
            for kw in kws:
                kw_text = " ".join(_tokens(kw))
                if kw_text and (kw_text in text or kw_text in normalized):
                    hits += 1
            scores.append(hits)
        best = max(scores, default=0)
        return scores.index(best) if best > 0 else None  # seri -> yang pertama

    def _similarity_pick(self, intent: dict, message: str) -> int | None:
        """Tanpa response_keywords: pilih respons yang paling mirip dengan pertanyaan.

        Skor respons = jumlah bobot kata pertanyaan yang ada di respons itu, dibagi
        akar-4 jumlah katanya (agar respons panjang tidak otomatis menang).
        Seri -> respons yang paling awal."""
        meta = self._resp_meta[intent["tag"]]
        seq = [t for t in self._normalize(message)
               if len(t) > 1 and t not in STOPWORDS and t not in QUESTION_WORDS and t not in GENERIC_WORDS]
        question = set(seq)
        text = " " + " ".join(_tokens(message)) + " "
        for phrase, extra in self.synonyms.items():
            if f" {phrase} " in text:
                question.update(extra)
        if not question:
            return None
        question_pairs = list(zip(seq, seq[1:]))
        n_base, df = meta["n_base"], meta["df"]

        def weight(token: str) -> float:  # 0 jika kata ada di semua respons inti
            return math.log((n_base + 1) / (df.get(token, 0) + 1))

        # Hanya jawaban inti yang dinilai: varian (inti + kalimat tambahan) memuat kata
        # unik di ekornya sehingga tidak adil bila ikut dibandingkan.
        scored = []
        for i in meta["bases"]:
            toks, resp_seq = meta["tokens"][i], meta["seqs"][i]
            total = 0.0
            for q in question:
                best = 0.0
                for t in toks:
                    if _tokens_match(q, t):
                        best = max(best, weight(t))
                total += best
            # Bonus: dua kata berurutan di pertanyaan juga berurutan di jawaban
            resp_pairs = list(zip(resp_seq, resp_seq[1:]))
            for q1, q2 in question_pairs:
                if any(_tokens_match(q1, r1) and _tokens_match(q2, r2) for r1, r2 in resp_pairs):
                    total += 1.0
            scored.append((total / (len(toks) ** 0.25) if toks else 0.0, -i, i))
        if not scored:
            return None
        top = max(scored)
        return top[2] if top[0] > 0 else None  # seri -> indeks terkecil

    def _pick_response(self, intent: dict, message: str, show_all: bool) -> str:
        """response_mode:
          "random"   : acak (cocok untuk sapaan, penutup, fallback)
          "relevant" : sesuai pertanyaan. Pakai response_keywords bila ada dan cocok,
                       jika tidak pakai kemiripan teks. Tak ada sinyal -> respons pertama.
          "all"      : tampilkan semua respons inti (mis. langkah darurat)
        """
        responses = intent.get("responses") or ["..."]
        mode = intent.get("response_mode", "random")
        if show_all or mode == "all":
            bases = self._resp_meta[intent["tag"]]["bases"] or [0]
            return "\n\n".join(responses[i] for i in bases)
        if mode == "relevant":
            idx = self._keyword_pick(intent, message)
            if idx is None:
                idx = self._similarity_pick(intent, message)
            return responses[idx if idx is not None else 0]
        return random.choice(responses)

    def _build(self, tag: str, score: float, urgent: bool, cat, message: str = "",
               show_all: bool = False) -> dict:
        intent = self.intents.get(tag) or self.intents[FALLBACK_TAG]
        text = self._pick_response(intent, message, show_all)

        pet = cat.name if cat is not None else DEFAULT_PET_NAME
        text = text.replace("{nama_kucing}", pet)

        # Personalisasi ringan untuk anak kucing (< 1 tahun)
        if cat is not None and (cat.age or 0) < 1 and tag in {"makanan_kucing", "jadwal_makan"}:
            text += (f"\n\n🍼 Catatan: {cat.name} masih anak kucing (di bawah 1 tahun), "
                     "jadi pilih makanan khusus kitten dan beri porsi lebih sering.")

        return {"tag": intent["tag"], "response": text, "score": score, "urgent": urgent}
