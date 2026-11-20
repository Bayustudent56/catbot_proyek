# CatBot - Manajemen Perawatan Kucing, Chatbot Intent JSON, dan Behavior Decoder

Aplikasi web Flask + SQLAlchemy + Bootstrap 5 (tema mint `#A8E6CF`) dengan fitur:
login (email/password dan Google OAuth), mode tamu, CRUD multi-kucing, chatbot berbasis `intents.json`
dengan riwayat percakapan yang tersimpan, dan Cat Mood & Behavior Decoder (3 input).

## Struktur proyek
```
catbot/
├── app.py               # routes: auth, Google OAuth, CRUD kucing, chat, decoder
├── config.py            # konfigurasi dari .env
├── models.py            # User, Cat, Conversation, ChatHistory (SQLAlchemy)
├── chatbot_engine.py    # mesin pencocokan intent + pemilihan jawaban
├── behavior_data.py     # matriks & logika Behavior Decoder + dokumentasi ilmiah
├── intents.json         # basis pengetahuan chatbot (17 intent)
├── templates/           # base, login, dashboard, cat_form, chat, decoder, partials
├── static/              # css/style.css, js/chat.js, js/decoder.js
├── requirements.txt
└── .env.example         # contoh konfigurasi (salin menjadi .env)
```

## Menjalankan
```bash
python3 -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # lalu isi SECRET_KEY
python app.py                                          # http://127.0.0.1:5000
```
Database SQLite `catbot.db` dibuat otomatis saat aplikasi pertama kali jalan.
Jika sebelumnya memakai versi lama, hapus `catbot.db` dulu (skema berubah).
Untuk MySQL: `pip install PyMySQL`, lalu di `.env` isi
`DATABASE_URL=mysql+pymysql://user:password@localhost/catbot`.

## Login Google (opsional)
1. Google Cloud Console > APIs & Services > Credentials > Create OAuth client ID (Web application).
2. Authorized redirect URI: `http://127.0.0.1:5000/auth/google/callback` (host harus sama persis dengan yang dibuka di browser).
3. Salin Client ID dan Secret ke `.env`. Tanpa itu, tombol Google nonaktif dan fitur lain tetap jalan.

## Struktur database
```mermaid
erDiagram
  USERS ||--o{ CATS : "punya"
  USERS ||--o{ CONVERSATIONS : "membuat"
  CATS |o--o{ CONVERSATIONS : "dibahas di"
  CONVERSATIONS ||--|{ CHAT_HISTORY : "berisi"
  USERS ||--o{ CHAT_HISTORY : "menulis"
  CATS |o--o{ CHAT_HISTORY : "terkait"
```
Semua relasi bersifat one-to-many. `cat_id` boleh kosong (NULL) untuk chat umum.
Menghapus user/kucing/percakapan menghapus data turunannya (cascade).
Aturan Behavior Decoder disimpan di `behavior_data.py`, bukan di tabel database.

## Riwayat chat
Seperti ChatGPT/Claude: satu kucing (atau chat umum) bisa punya banyak percakapan.
Membuka ruang chat memulai percakapan baru; item di "Riwayat percakapan" bisa dibuka dan dilanjutkan.
Satu percakapan atau semuanya dapat dihapus. Mode tamu tidak menyimpan apa pun.

## Cara kerja chatbot (`chatbot_engine.py`)
1. **Darurat dulu.** Jika pesan memuat salah satu `urgent_keywords`, langsung dijawab intent
   `darurat_kesehatan` (semua langkah ditampilkan).
2. **Normalisasi.** Huruf kecil, buang tanda baca, koreksi typo ringan, lepas akhiran -nya.
3. **Skoring tiap pola.** Frasa pola muncul utuh = skor 1.0; selain itu overlap kata berbobot IDF
   (kata umum seperti "kucing" berbobot kecil). Intent dengan skor tertinggi dipilih.
4. **Threshold dan fallback.** Skor di bawah `threshold` (0.45) atau tanpa kecocokan -> intent `fallback`.
5. **Memilih jawaban** sesuai `response_mode` pada intent:

| `response_mode` | Perilaku |
|---|---|
| `random` | Jawaban acak. Cocok untuk `salam`, `penutup`, `fallback`. |
| `relevant` | Jawaban yang paling sesuai dengan pertanyaan. Memakai `response_keywords` bila ada, jika tidak memakai kemiripan teks (kata berbobot, pemotong imbuhan, bonus frasa berurutan, kamus sinonim). Tanpa sinyal -> jawaban pertama. |
| `all` | Semua jawaban inti ditampilkan (dipakai untuk `darurat_kesehatan`). |

Tiap intent memiliki sekitar 5 jawaban inti; sisanya adalah varian (jawaban inti + kalimat tambahan).
Untuk mode `relevant`, hanya jawaban inti yang dinilai.

## Format `intents.json`
```json
{
  "meta": {...},
  "threshold": 0.45,
  "disclaimer": "...",
  "urgent_keywords": ["kejang", "muntah darah", "..."],
  "quick_replies": [ {"label": "Vaksin", "message": "Jadwal vaksin kucing"} ],
  "synonyms": { "tidak boleh": ["hindari", "dihindari"] },
  "intents": [
    { "tag": "...", "description": "...", "response_mode": "random | relevant | all",
      "patterns": ["..."], "responses": ["..."],
      "response_keywords": [["kata", "kunci"], ["..."]] }
  ]
}
```
- `quick_replies` boleh teks biasa atau objek `{label, message}`.
- `synonyms` (opsional) menambah kamus sinonim bawaan di `chatbot_engine.py`.
- `response_keywords` (opsional): daftar ke-i dipasangkan dengan `responses[i]`.
- `{nama_kucing}` pada respons diganti nama kucing aktif, atau "si meong" pada chat umum.
- Menambah pola (`patterns`) adalah cara paling efektif agar chatbot mengenali pertanyaan baru.
- Catatan: pola `kucing tidak mau makan` muncul di dua intent (`jadwal_makan` dan `kesehatan_kucing`);
  yang dipakai adalah intent yang lebih dulu di file.

## Behavior Decoder
Sistem pakar berbasis aturan: skor berbobot (ekor 0.35, telinga 0.35, suara 0.30) ditambah aturan
kombinasi khusus R1-R6. Sumber rujukan: ASPCA, International Cat Care, Bradshaw (2013), Overall (2013).
Bobot adalah operasionalisasi penulis atas deskripsi pada literatur, bukan hasil studi kuantitatif.
Penjelasan lengkap ada di docstring `behavior_data.py`. Verifikasi ulang sitasi sebelum dipakai di laporan.

## Keamanan dan Git
- `.env`, `venv/`, dan `*.db` sudah ada di `.gitignore`. Jangan pernah meng-commit `.env`.
- Semua form dan permintaan `/api/*` dilindungi CSRF. Password disimpan sebagai hash.
- Informasi kesehatan bersifat umum dan bukan pengganti dokter hewan.
