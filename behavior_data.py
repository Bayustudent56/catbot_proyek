"""Cat Mood & Behavior Decoder - data dan logika (3 input bersamaan).

LANDASAN AKADEMIK (untuk dijelaskan ke dosen)
---------------------------------------------
Metode  : sistem pakar berbasis aturan (rule-based expert system) dengan
          weighted multi-cue scoring + aturan kombinasi khusus (override).
Sumber  : interpretasi tiap sinyal (ekor, telinga, suara/aksi) mengacu pada
          panduan umum bahasa tubuh kucing dalam literatur felinologi populer dan klinis:
          - ASPCA, panduan perilaku kucing (aspca.org) dan International Cat Care
            (icatcare.org), artikel "Understanding cat body language".
          - Bradshaw, J. (2013). Cat Sense. Basic Books.
          - Overall, K. (2013). Manual of Clinical Behavioral Medicine for Dogs and Cats. Elsevier.
          - Crowell-Davis, Curtis & Knowles (2004). Social organization in the cat: a modern
            understanding. Journal of Feline Medicine and Surgery, 6(1).
          (Verifikasi ulang sitasi & halaman sebelum dimasukkan ke laporan.)

Cara kerja:
  1. Tiap opsi punya "profil skor" 0-3 terhadap 7 kategori suasana hati. Skor ini
     adalah operasionalisasi penulis atas deskripsi pada literatur di atas
     (bukan angka hasil penelitian kuantitatif) dan terbuka untuk dikalibrasi.
  2. Skor tiap suasana hati = jumlah (bobot input x skor opsi).
     Bobot: ekor 0.35, telinga 0.35, suara/aksi 0.30. Telinga dan ekor dianggap
     sinyal visual yang paling konsisten, suara lebih ambigu (mis. purring bisa
     berarti senang maupun menenangkan diri saat sakit/stres).
  3. Aturan kombinasi (RULES) menimpa hasil skor untuk pola khas atau pola yang
     menyesatkan bila dibaca satu per satu (contoh: purring + telinga menempel).
  4. Tie-break memakai prinsip kehati-hatian (safety first): suasana yang berisiko
     (agresif/takut/tidak nyaman) didahulukan.
  5. Tingkat keyakinan = seberapa banyak sinyal yang sejalan dengan hasil akhir.
     Satu sinyal saja -> keyakinan rendah; sinyal bertentangan -> rendah.

Keterbatasan: bahasa tubuh harus dibaca utuh bersama konteks (mata, postur, situasi).
Aplikasi ini edukatif dan bukan alat diagnosis.
"""
from __future__ import annotations

WEIGHTS = {"tail": 0.35, "ears": 0.35, "sound": 0.30}

# Urutan prioritas (kehati-hatian) saat skor seri
MOOD_PRIORITY = ["agresif", "takut", "tidak_nyaman", "cemas", "penasaran", "rileks", "sayang"]

CATEGORY_LABELS = {"tail": "Bentuk Ekor", "ears": "Posisi Telinga", "sound": "Suara / Aksi"}

# Id opsi = nilai data-v pada elemen SVG (_cat_svg.html) agar preview sinkron.
OPTIONS: dict[str, list[dict]] = {
    "tail": [
        {"id": "up", "label": "Tegak melengkung", "hint": "Santai, ramah, dan siap menyapa",
         "reading": "Ekor tegak dengan ujung melengkung adalah sapaan ramah.",
         "scores": {"sayang": 3, "rileks": 2, "penasaran": 1}},
        {"id": "puffed", "label": "Mengembang besar", "hint": "Kaget atau merasa terancam",
         "reading": "Bulu ekor berdiri (piloereksi) membuat tubuh tampak lebih besar saat takut.",
         "scores": {"takut": 3, "agresif": 2, "cemas": 1}},
        {"id": "curled", "label": "Melingkar ke bawah", "hint": "Ragu dan kurang percaya diri",
         "reading": "Ekor rendah dan melingkar menandakan kucing waspada dan kurang yakin.",
         "scores": {"cemas": 3, "takut": 2, "tidak_nyaman": 1}},
        {"id": "tucked", "label": "Menyelip di antara kaki", "hint": "Takut dan ingin mengecilkan diri",
         "reading": "Ekor terselip di bawah tubuh adalah sinyal takut atau tunduk.",
         "scores": {"takut": 3, "cemas": 2, "tidak_nyaman": 1}},
        {"id": "lash", "label": "Mengibas cepat", "hint": "Kesal atau sangat fokus",
         "reading": "Ekor mencambuk cepat sering muncul saat kucing kesal atau terstimulasi berlebihan.",
         "scores": {"agresif": 3, "cemas": 1, "penasaran": 1}},
    ],
    "ears": [
        {"id": "normal", "label": "Tegak normal", "hint": "Santai dan tenang",
         "reading": "Telinga tegak netral menandakan kucing santai.",
         "scores": {"rileks": 3, "penasaran": 1}},
        {"id": "forward", "label": "Menghadap depan", "hint": "Tertarik dan waspada",
         "reading": "Telinga condong ke depan menandakan perhatian pada sesuatu yang menarik.",
         "scores": {"penasaran": 3, "rileks": 1}},
        {"id": "airplane", "label": "Miring / airplane ears", "hint": "Gelisah atau ragu",
         "reading": "Telinga melebar ke samping menandakan kucing gelisah, kesal, atau bimbang.",
         "scores": {"cemas": 3, "agresif": 1, "takut": 1}},
        {"id": "flat", "label": "Menempel ke belakang", "hint": "Takut atau siap membela diri",
         "reading": "Telinga datar ke belakang melindungi telinga saat takut atau akan berkelahi.",
         "scores": {"takut": 3, "agresif": 3, "tidak_nyaman": 1}},
    ],
    "sound": [
        {"id": "purr", "label": "Mendengkur (purring)", "hint": "Nyaman, kadang menenangkan diri",
         "reading": "Purring umumnya tanda nyaman, tetapi juga dipakai kucing untuk menenangkan diri.",
         "scores": {"rileks": 2, "sayang": 2, "tidak_nyaman": 1}},
        {"id": "hiss", "label": "Mendesis (hissing)", "hint": "Peringatan: jangan mendekat",
         "reading": "Desisan adalah peringatan defensif agar ancaman menjauh.",
         "scores": {"agresif": 3, "takut": 3}},
        {"id": "knead", "label": "Menginjak-injak (kneading)", "hint": "Nyaman dan penuh kasih",
         "reading": "Kneading adalah sisa kebiasaan menyusu yang muncul saat kucing merasa aman.",
         "scores": {"sayang": 3, "rileks": 3}},
        {"id": "trill", "label": "Mengeong pelan / trill", "hint": "Menyapa dengan ramah",
         "reading": "Trill atau meong pendek yang lembut adalah sapaan akrab.",
         "scores": {"sayang": 3, "penasaran": 1}},
        {"id": "yowl", "label": "Melolong / meong keras", "hint": "Cemas atau tidak nyaman",
         "reading": "Lolongan panjang dapat menandakan cemas, bingung, atau rasa tidak nyaman.",
         "scores": {"cemas": 3, "tidak_nyaman": 2}},
    ],
}

_INDEX = {cat: {o["id"]: o for o in opts} for cat, opts in OPTIONS.items()}

MOODS: dict[str, dict] = {
    "rileks": {
        "badge": "Rileks & percaya diri", "tone": "calm",
        "quote": "Aku nyaman dan merasa aman di sini.",
        "summary": "Tubuhnya santai tanpa tanda tekanan. Ia merasa aman dengan lingkungannya.",
        "insight": "Sinyal tubuh yang netral dan lembut menunjukkan kucing percaya pada situasi dan orang di sekitarnya.",
        "tips": ["Biarkan ia menikmati waktu tenangnya.",
                 "Jaga rutinitas makan dan bermain tetap konsisten.",
                 "Beri belaian hanya jika ia mendekat."],
        "vet_warning": None,
    },
    "sayang": {
        "badge": "Penuh kasih sayang", "tone": "calm",
        "quote": "Aku senang melihatmu!",
        "summary": "Ia menyapa dan merasa dekat denganmu. Ini sapaan ramah khas kucing.",
        "insight": "Ekor, suara lembut, dan perilaku menginjak-injak adalah perilaku yang dipelajari sejak anak kucing menyusu pada induknya, dan ditujukan ke yang dipercaya.",
        "tips": ["Sapa dengan lembut dan biarkan ia mendekat.",
                 "Tawarkan tangan untuk diendus, tanpa memaksa.",
                 "Ajak bermain sebentar jika ia merespons positif."],
        "vet_warning": None,
    },
    "penasaran": {
        "badge": "Waspada & penasaran", "tone": "alert",
        "quote": "Hmm, apa itu? Aku mau lihat.",
        "summary": "Perhatiannya tertuju pada sesuatu. Ia siaga tetapi belum terancam.",
        "insight": "Telinga dan tubuh yang condong ke depan menandakan kucing mengumpulkan informasi sebelum memutuskan mendekat atau menghindar.",
        "tips": ["Beri waktu agar ia mengamati sendiri.",
                 "Alihkan dengan mainan jika objeknya tidak aman.",
                 "Hindari gerakan mendadak."],
        "vet_warning": None,
    },
    "cemas": {
        "badge": "Cemas / kurang nyaman", "tone": "alert",
        "quote": "Aku kurang yakin dengan situasi ini...",
        "summary": "Ia ragu dan mulai gelisah. Belum defensif, tetapi sedang butuh rasa aman.",
        "insight": "Sinyal yang bercampur (ragu, rendah, gelisah) khas kucing yang menilai situasi sebagai kurang aman.",
        "tips": ["Kurangi kebisingan dan keramaian di sekitarnya.",
                 "Sediakan tempat bersembunyi atau area tinggi yang tenang.",
                 "Jangan dipaksa digendong atau didekati."],
        "vet_warning": "Jika cemas terjadi terus-menerus atau tiba-tiba, konsultasikan ke dokter hewan.",
    },
    "takut": {
        "badge": "Takut & defensif", "tone": "danger",
        "quote": "Tolong beri aku ruang!",
        "summary": "Ia merasa terancam dan ingin menghindar. Jika terpojok, ia bisa menyerang untuk melindungi diri.",
        "insight": "Ekor mengembang atau terselip, telinga datar, dan desisan adalah pertahanan diri (defensive threat display), bukan tanda kucing 'jahat'.",
        "tips": ["Berhenti mendekat dan beri ruang untuk kabur.",
                 "Hilangkan sumber ketakutan (suara keras, hewan lain).",
                 "Jangan menyentuh atau menghukum; tunggu hingga ia tenang."],
        "vet_warning": "Jika ketakutan muncul tanpa sebab jelas, periksa ke dokter hewan.",
    },
    "agresif": {
        "badge": "Terancam & siap membela diri", "tone": "danger",
        "quote": "Jangan mendekat!",
        "summary": "Ia sangat kesal atau terprovokasi. Risiko mencakar atau menggigit meningkat.",
        "insight": "Ekor mencambuk, telinga ke belakang, dan desisan adalah rangkaian peringatan sebelum menyerang.",
        "tips": ["Mundur perlahan dan jangan menatap langsung.",
                 "Jauhkan dari kucing atau orang lain sampai tenang.",
                 "Jangan menggunakan tangan untuk memisahkan; alihkan dengan suara atau penghalang."],
        "vet_warning": "Agresi mendadak bisa disebabkan rasa sakit. Jika berulang, hubungi dokter hewan.",
    },
    "tidak_nyaman": {
        "badge": "Tidak nyaman / mungkin sakit", "tone": "alert",
        "quote": "Ada yang tidak enak di badanku.",
        "summary": "Sinyalnya bertentangan dengan suasana hati senang. Ia bisa sedang menenangkan diri.",
        "insight": "Purring yang disertai telinga atau ekor bertanda tekanan dapat berarti kucing menenangkan diri saat stres atau sakit.",
        "tips": ["Perhatikan nafsu makan, minum, dan buang air.",
                 "Beri tempat tenang dan hangat.",
                 "Catat sejak kapan perilaku ini muncul."],
        "vet_warning": "Jika berlangsung lebih dari sehari atau disertai lemas/tidak mau makan, hubungi dokter hewan.",
    },
}

# Aturan kombinasi: bila SEMUA kondisi `when` terpenuhi (hanya pada input yang dipilih),
# hasil akhir dipaksa ke `mood`.
RULES = [
    {"id": "R1", "when": {"tail": {"puffed"}, "ears": {"flat"}, "sound": {"hiss"}}, "mood": "takut",
     "note": "Pola 'defensive threat display': ekor mengembang + telinga datar + desisan."},
    {"id": "R2", "when": {"sound": {"purr"}, "ears": {"flat", "airplane"}}, "mood": "tidak_nyaman",
     "note": "Purring bersama telinga tertekan: kucing mungkin menenangkan diri, bukan senang."},
    {"id": "R3", "when": {"sound": {"purr"}, "tail": {"tucked"}}, "mood": "tidak_nyaman",
     "note": "Purring dengan ekor terselip: waspada, bisa jadi stres atau nyeri."},
    {"id": "R4", "when": {"sound": {"yowl"}, "tail": {"tucked"}}, "mood": "tidak_nyaman",
     "note": "Melolong dengan ekor terselip: tanda tidak nyaman, perlu pengamatan lebih lanjut."},
    {"id": "R5", "when": {"sound": {"knead"}, "tail": {"up"}}, "mood": "sayang",
     "note": "Kneading + ekor tegak: ungkapan kasih sayang dan rasa aman."},
    {"id": "R6", "when": {"tail": {"up"}, "ears": {"normal"}, "sound": {"trill"}}, "mood": "sayang",
     "note": "Ekor tegak + telinga normal + trill: pola sapaan (greeting) ramah."},
]

REFERENCES = [
    "ASPCA - panduan perilaku kucing (aspca.org)",
    "International Cat Care - Understanding cat body language (icatcare.org)",
    "Bradshaw, J. (2013). Cat Sense. Basic Books.",
    "Overall, K. (2013). Manual of Clinical Behavioral Medicine for Dogs and Cats. Elsevier.",
]


def get_decoder_options() -> dict:
    """Versi aman untuk dikirim ke browser (tanpa profil skor)."""
    return {
        cat: {
            "label": CATEGORY_LABELS[cat],
            "options": [{"id": o["id"], "label": o["label"], "hint": o["hint"]} for o in opts],
        }
        for cat, opts in OPTIONS.items()
    }


def _match_rule(chosen: dict[str, str]) -> dict | None:
    for rule in RULES:
        if all(chosen.get(cat) in allowed for cat, allowed in rule["when"].items()):
            return rule
    return None


def decode_behavior(tail: str | None = None, ears: str | None = None, sound: str | None = None) -> dict:
    chosen = {"tail": tail or None, "ears": ears or None, "sound": sound or None}
    selected: dict[str, dict] = {}
    for cat, opt_id in chosen.items():
        if not opt_id:
            continue
        option = _INDEX[cat].get(opt_id)
        if option is None:
            return {"ok": False, "error": f"Pilihan untuk {CATEGORY_LABELS[cat]} tidak dikenali."}
        selected[cat] = option
    if not selected:
        return {"ok": False, "error": "Pilih minimal satu sinyal (ekor, telinga, atau suara)."}

    totals = {m: 0.0 for m in MOODS}
    for cat, option in selected.items():
        for mood, value in option["scores"].items():
            totals[mood] += WEIGHTS[cat] * value

    rule = _match_rule({c: o["id"] for c, o in selected.items()})
    if rule:
        winner = rule["mood"]
    else:
        winner = max(MOOD_PRIORITY, key=lambda m: (round(totals[m], 4), -MOOD_PRIORITY.index(m)))

    support = [c for c, o in selected.items() if o["scores"].get(winner, 0) >= 2]
    ratio = len(support) / len(selected)
    conflicting = [CATEGORY_LABELS[c] for c in selected if c not in support]
    if rule:
        confidence = {"label": "Tinggi", "note": f"Cocok dengan pola khusus {rule['id']}."}
    elif len(selected) == 1:
        confidence = {"label": "Rendah", "note": "Baru satu sinyal yang dibaca. Tambahkan ekor, telinga, atau suara."}
    elif ratio == 1:
        confidence = {"label": "Tinggi", "note": "Semua sinyal yang dipilih sejalan."}
    elif ratio >= 0.66:
        confidence = {"label": "Sedang", "note": f"Sebagian besar sinyal sejalan; {', '.join(conflicting)} kurang cocok."}
    else:
        confidence = {"label": "Rendah", "note": "Sinyal saling bertentangan. Amati lebih lama dan lihat konteks."}

    total_sum = sum(totals.values()) or 1.0
    top = sorted(totals.items(), key=lambda kv: (-kv[1], MOOD_PRIORITY.index(kv[0])))[:3]
    scores = [{"mood": MOODS[m]["badge"], "pct": round(v / total_sum * 100)} for m, v in top if v > 0]

    mood = MOODS[winner]
    return {
        "ok": True,
        "mood": winner,
        "badge": mood["badge"],
        "tone": mood["tone"],
        "quote": mood["quote"],
        "summary": mood["summary"],
        "insight": mood["insight"],
        "tips": mood["tips"],
        "vet_warning": mood["vet_warning"],
        "confidence": confidence,
        "rule": {"id": rule["id"], "note": rule["note"]} if rule else None,
        "signals": [
            {"category": CATEGORY_LABELS[c], "label": o["label"], "reading": o["reading"]}
            for c, o in selected.items()
        ],
        "scores": scores,
        "references": REFERENCES,
    }
