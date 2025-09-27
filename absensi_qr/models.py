# ======================== DATABASE MODELS ========================
# Berkas ini mendefinisikan struktur tabel (models) untuk database menggunakan SQLAlchemy.

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import time

# Inisialisasi objek SQLAlchemy
db = SQLAlchemy()


# --- Model untuk data Kelas ---
class Kelas(db.Model):
    """
    Model ini merepresentasikan tabel 'kelas' di database.
    Digunakan untuk mengelola data kelas secara terpisah.
    """
    __tablename__ = 'kelas'
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)

    # Relasi balik ke tabel Siswa
    siswa_list: Mapped[list["Siswa"]] = relationship(back_populates="kelas_relasi")

    def __repr__(self):
        return f'<Kelas {self.nama}>'


# --- Model untuk data Siswa ---
class Siswa(db.Model):
    """
    Model ini merepresentasikan tabel 'siswa' di database.
    Digunakan untuk menyimpan informasi dasar setiap siswa.
    """
    __tablename__ = 'siswa'
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    nis: Mapped[str] = mapped_column(db.String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(db.String(100), nullable=False)
    # Kolom 'kelas' diubah menjadi 'kelas_id' sebagai foreign key
    kelas_id: Mapped[int] = mapped_column(db.ForeignKey('kelas.id'), nullable=False)
    no_hp_ortu: Mapped[str] = mapped_column(db.String(20))
    qr_path: Mapped[str] = mapped_column(db.String(200))

    # Relasi ke tabel Kelas
    kelas_relasi: Mapped["Kelas"] = relationship(back_populates="siswa_list")

    def __repr__(self):
        return f'<Siswa {self.nama}>'


# --- Model untuk data Absensi ---
class Absensi(db.Model):
    """
    Model ini merepresentasikan tabel 'absensi' di database.
    Setiap baris mencatat satu kejadian absensi (masuk atau pulang) siswa.
    """
    __tablename__ = 'absensi'
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    nis: Mapped[str] = mapped_column(db.String(20), nullable=False)
    tanggal: Mapped[datetime.date] = mapped_column(db.Date, default=datetime.now().date)
    waktu: Mapped[datetime.time] = mapped_column(db.Time, default=datetime.now().time)
    status: Mapped[str] = mapped_column(db.String(20), nullable=True, default=None)
    keterangan: Mapped[str] = mapped_column(db.String(100), nullable=True)
    jenis_absen: Mapped[str] = mapped_column(db.String(10), nullable=True)


# --- Model untuk Pengaturan Waktu ---
class SettingWaktu(db.Model):
    """
    Model ini merepresentasikan tabel 'setting_waktu' di database.
    Digunakan untuk menyimpan rentang waktu yang diizinkan untuk absensi.
    """
    __tablename__ = 'setting_waktu'
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    jam_masuk_mulai: Mapped[time] = mapped_column(db.Time, nullable=False)
    jam_masuk_selesai: Mapped[time] = mapped_column(db.Time, nullable=False)
    jam_pulang_mulai: Mapped[time] = mapped_column(db.Time, nullable=False)
    jam_pulang_selesai: Mapped[time] = mapped_column(db.Time, nullable=False)
    jam_terlambat_selesai: Mapped[time] = mapped_column(db.Time, nullable=True)