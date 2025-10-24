# Sistem Absensi Siswa Berbasis QR Code

Proyek sederhana berbasis Flask untuk manajemen absensi siswa dan pegawai menggunakan QR code.

## Ringkasan

Aplikasi ini menyediakan:
- Pendaftaran dan pengelolaan data siswa & pegawai
- Pembuatan dan penyimpanan QR code untuk siswa/pegawai di `static/qr_codes/`
- Pencatatan absensi (siswa & pegawai)
- Export laporan absensi
- Pengaturan waktu masuk/pulang dan hari libur

Dibangun dengan Flask, SQLAlchemy, dan beberapa library pendukung (lihat `requirements.txt`).

## Persyaratan

- Python 3.8+ (disarankan)
- MySQL (atau server database yang kompatibel dengan konektor yang dipakai)
- Virtual environment (disarankan)

## Instalasi (Windows — PowerShell)

1. Clone repository atau unduh isi folder proyek.
2. Masuk ke folder proyek:

```powershell
cd d:\Sistem-Absensi-Siswa-Berbasis-QR-Code\absensi-qr
```

3. Buat dan aktifkan virtual environment (opsional tapi disarankan):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

4. Install dependensi:

```powershell
pip install -r requirements.txt
```

5. Buat file `.env` di root proyek dan isi variabel berikut sesuai lingkungan Anda:

```
DB_USER=nama_user_db
DB_PASSWORD=password_db
DB_HOST=host_db (contoh: localhost)
DB_NAME=nama_database
ADMIN_USERNAME=admin
ADMIN_PASSWORD=123
```

Aplikasi menggunakan `python-dotenv` sehingga cukup menaruh variabel di file `.env`.

6. Pastikan MySQL berjalan dan kredensial pada `.env` benar. Aplikasi akan membuat tabel yang diperlukan secara otomatis saat pertama dijalankan.

## Menjalankan aplikasi

Jalankan dari PowerShell:

```powershell
python app.py
```

Aplikasi akan berjalan di http://0.0.0.0:5000 (akses lewat http://localhost:5000 pada mesin lokal).

Default login admin: username `admin`, password `123` — kecuali Anda mengubahnya di `.env`.

## Struktur penting

- `app.py` — entry point dan konfigurasi Flask
- `models.py` — definisi model database (SQLAlchemy)
- `templates/` — template HTML (UI)
- `static/qr_codes/siswa/` — QR code siswa
- `static/qr_codes/pegawai/` — QR code pegawai
- `requirements.txt` — daftar dependensi
- `*.py` lainnya (`*_routes.py`) — blueprint route untuk fitur-fitur aplikasi

## Perhatian / Troubleshooting

- Error koneksi DB: pastikan MySQL berjalan dan variabel `.env` benar.
- Permission: pastikan folder `static/qr_codes/` dapat ditulisi oleh aplikasi.
- Jika tabel tidak muncul: pastikan database dengan nama `DB_NAME` telah dibuat, aplikasi akan membuat tabelnya sendiri jika koneksi berhasil.

