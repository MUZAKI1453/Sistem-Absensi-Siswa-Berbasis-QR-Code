# ======================== DATABASE MODELS ========================
# Berkas ini mendefinisikan struktur tabel (models) untuk database menggunakan SQLAlchemy.

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Inisialisasi objek SQLAlchemy
db = SQLAlchemy()

# --- Model untuk data Siswa ---
class Siswa(db.Model):
    """
    Model ini merepresentasikan tabel 'siswa' di database.
    Digunakan untuk menyimpan informasi dasar setiap siswa.
    """
    id = db.Column(db.Integer, primary_key=True)  # Kunci utama, nilai unik untuk setiap siswa
    nis = db.Column(db.String(20), unique=True, nullable=False) # NIS, bersifat unik & tidak boleh kosong
    nama = db.Column(db.String(100), nullable=False) # Nama siswa, tidak boleh kosong
    kelas = db.Column(db.String(50)) # Kelas siswa
    no_hp_ortu = db.Column(db.String(20)) # Nomor HP orang tua
    qr_path = db.Column(db.String(200)) # Lokasi file QR code yang disimpan

# --- Model untuk data Absensi ---
class Absensi(db.Model):
    """
    Model ini merepresentasikan tabel 'absensi' di database.
    Setiap baris mencatat satu kejadian absensi (masuk atau pulang) siswa.
    """
    id = db.Column(db.Integer, primary_key=True) # Kunci utama
    nis = db.Column(db.String(20), nullable=False) # NIS siswa yang melakukan absensi
    tanggal = db.Column(db.Date, default=datetime.now().date) # Tanggal absensi (otomatis terisi)
    waktu = db.Column(db.Time, default=datetime.now().time) # Waktu absensi (otomatis terisi)
    status = db.Column(db.String(20), nullable=True, default=None)  # Status kehadiran (Hadir, Sakit, Izin)
    keterangan = db.Column(db.String(100)) # Keterangan tambahan (misal: alasan sakit/izin)
    keterlambatan = db.Column(db.Boolean, default=False) # Status keterlambatan (True/False)
    jenis_absen = db.Column(db.String(10), nullable=True) # Jenis absensi: 'masuk' atau 'pulang'

# --- Model untuk Pengaturan Waktu ---
class SettingWaktu(db.Model):
    """
    Model ini merepresentasikan tabel 'setting_waktu' di database.
    Digunakan untuk menyimpan rentang waktu yang diizinkan untuk absensi.
    """
    id = db.Column(db.Integer, primary_key=True) # Kunci utama
    jam_masuk_mulai = db.Column(db.Time) # Waktu mulai absensi masuk
    jam_masuk_selesai = db.Column(db.Time) # Waktu selesai absensi masuk
    jam_pulang_mulai = db.Column(db.Time) # Waktu mulai absensi pulang
    jam_pulang_selesai = db.Column(db.Time) # Waktu selesai absensi pulang