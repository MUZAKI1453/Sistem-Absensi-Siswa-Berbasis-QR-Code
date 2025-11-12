# ======================== DATABASE MODELS ========================
# Berkas ini mendefinisikan struktur tabel (models) untuk database menggunakan SQLAlchemy.

from datetime import datetime, time, date

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, ForeignKey, String, Integer, Date, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Inisialisasi objek SQLAlchemy
db = SQLAlchemy()


# --- Model untuk data Kelas ---
class Kelas(db.Model):
    """Model tabel 'kelas' untuk mengelola data kelas."""
    __tablename__ = 'kelas'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    siswa_list: Mapped[list["Siswa"]] = relationship(back_populates="kelas_relasi")

    def __repr__(self):
        return f'<Kelas {self.nama}>'


# --- Model untuk data Siswa ---
class Siswa(db.Model):
    """Model tabel 'siswa' untuk menyimpan data siswa dasar."""
    __tablename__ = 'siswa'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nis: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    kelas_id: Mapped[int] = mapped_column(ForeignKey('kelas.id'), nullable=False)
    no_hp_ortu: Mapped[str] = mapped_column(String(20), nullable=True)
    qr_path: Mapped[str] = mapped_column(String(200), nullable=True)
    kelas_relasi: Mapped["Kelas"] = relationship(back_populates="siswa_list")

    def __repr__(self):
        return f'<Siswa {self.nama}>'


# --- Model untuk data Absensi Siswa ---
class Absensi(db.Model):
    """Model tabel 'absensi' untuk catatan absensi siswa (masuk/pulang)."""
    __tablename__ = 'absensi'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nis: Mapped[str] = mapped_column(String(20), nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, default=datetime.now().date)
    waktu: Mapped[time] = mapped_column(Time, default=datetime.now().time)
    status: Mapped[str] = mapped_column(String(20), nullable=True, default=None)
    keterangan: Mapped[str] = mapped_column(String(100), nullable=True)
    jenis_absen: Mapped[str] = mapped_column(String(10), nullable=True)


# --- Model untuk Pengaturan Waktu Siswa ---
class SettingWaktu(db.Model):
    """Model tabel 'setting_waktu' untuk rentang waktu absensi siswa."""
    __tablename__ = 'setting_waktu'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jam_masuk_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_masuk_selesai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_pulang_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_pulang_selesai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_terlambat_selesai: Mapped[time] = mapped_column(Time, nullable=True)

    # ==============================================================================
    #  PENAMBAHAN BARU: Kolom untuk menyimpan hari libur rutin (mingguan)
    # ==============================================================================
    hari_libur_rutin: Mapped[str] = mapped_column(String(100), nullable=True, default='Sabtu,Minggu')


# --- Model untuk data Pegawai (Staf/Guru/Keamanan) ---
class Pegawai(db.Model):
    """Model tabel 'pegawai' untuk data guru, staf, dan keamanan dengan role."""
    __tablename__ = 'pegawai'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    no_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    shift: Mapped[str] = mapped_column(String(10), nullable=True)

    qr_path: Mapped[str] = mapped_column(String(200), nullable=True)

    # PERUBAHAN: Menambahkan cascade="all, delete-orphan" untuk menghapus data terkait secara otomatis
    absensi_list: Mapped[list["AbsensiPegawai"]] = relationship(back_populates="pegawai_relasi",
                                                                cascade="all, delete-orphan")
    jadwal_keamanan_list: Mapped[list["JadwalKeamanan"]] = relationship(back_populates="pegawai_relasi",
                                                                        cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Pegawai {self.nama} (Role: {self.role})>'


# --- Model untuk Jadwal Keamanan ---
class JadwalKeamanan(db.Model):
    """Model tabel untuk menyimpan penetapan shift keamanan per hari."""
    __tablename__ = 'jadwal_keamanan'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pegawai_id: Mapped[int] = mapped_column(ForeignKey('pegawai.id'), nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[str] = mapped_column(String(10), nullable=False)

    pegawai_relasi: Mapped["Pegawai"] = relationship(back_populates="jadwal_keamanan_list")
    __table_args__ = (UniqueConstraint('pegawai_id', 'tanggal', name='_pegawai_tanggal_uc'),)

    def __repr__(self):
        return f'<Jadwal Keamanan Pegawai ID:{self.pegawai_id} Tanggal:{self.tanggal} Shift:{self.shift}>'


# --- Model untuk data AbsensiPegawai ---
class AbsensiPegawai(db.Model):
    """Model tabel 'absensi_pegawai' untuk catatan absensi pegawai."""
    __tablename__ = 'absensi_pegawai'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    no_id: Mapped[str] = mapped_column(String(20), ForeignKey('pegawai.no_id'), nullable=False)
    tanggal: Mapped[date] = mapped_column(Date, default=datetime.now().date)
    waktu: Mapped[time] = mapped_column(Time, default=datetime.now().time)
    status: Mapped[str] = mapped_column(String(20), nullable=True, default=None)
    keterangan: Mapped[str] = mapped_column(String(100), nullable=True)
    jenis_absen: Mapped[str] = mapped_column(String(10), nullable=True)
    pegawai_relasi: Mapped["Pegawai"] = relationship(back_populates="absensi_list")


# --- Model untuk Pengaturan Waktu Guru & Staf ---
class SettingWaktuGuruStaf(db.Model):
    """Model tabel untuk rentang waktu absensi Guru dan Staf."""
    __tablename__ = 'setting_waktu_guru_staf'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jam_masuk_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_masuk_selesai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_terlambat_selesai: Mapped[time] = mapped_column(Time, nullable=True)
    jam_pulang_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_pulang_selesai: Mapped[time] = mapped_column(Time, nullable=False)


# --- Model untuk Pengaturan Waktu Keamanan (Shift) ---
class SettingWaktuKeamanan(db.Model):
    """Model tabel untuk rentang waktu absensi Keamanan per shift."""
    __tablename__ = 'setting_waktu_keamanan'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nama_shift: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    jam_masuk_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_masuk_selesai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_terlambat_selesai: Mapped[time] = mapped_column(Time, nullable=True)
    jam_pulang_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_pulang_selesai: Mapped[time] = mapped_column(Time, nullable=False)


# --- Model untuk Hari Libur Spesial ---
class HariLibur(db.Model):
    """Model tabel untuk menyimpan tanggal-tanggal libur spesial."""
    __tablename__ = 'hari_libur'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tanggal: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    keterangan: Mapped[str] = mapped_column(String(150), nullable=False)

    def __repr__(self):
        return f'<HariLibur {self.tanggal.strftime("%Y-%m-%d")}: {self.keterangan}>'



class IzinSiswa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_ortu = db.Column(db.String(100), nullable=False)
    no_wa = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    nama_siswa = db.Column(db.String(100), nullable=False)
    kelas = db.Column(db.String(50))
    wali_kelas = db.Column(db.String(100))
    jenis_izin = db.Column(db.String(20), nullable=False)  # 'Sakit' atau 'Izin'
    keterangan = db.Column(db.Text)
    file_surat = db.Column(db.String(255))
    file_foto = db.Column(db.String(255))
    tanggal = db.Column(db.Date, default=datetime.now().date)
    status = db.Column(db.String(20), default="Menunggu Persetujuan")  # 'Menunggu', 'Disetujui', 'Ditolak'