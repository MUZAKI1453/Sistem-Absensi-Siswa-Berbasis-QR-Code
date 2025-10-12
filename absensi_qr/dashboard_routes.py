from datetime import datetime, time

from flask import Blueprint, render_template

from models import SettingWaktu, Siswa, Kelas, Absensi, Pegawai, AbsensiPegawai
from utils import check_admin_session


dashboard_bp = Blueprint("dashboard_bp", __name__, url_prefix="/dashboard")

# =======================================================================
#  ROUTE: DASHBOARD UTAMA
# =======================================================================
@dashboard_bp.route("/dashboard")
def dashboard():
    """Tampilkan dashboard dengan statistik absensi hari ini."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Ambil tanggal dan waktu saat ini
    hari_ini = datetime.today().date()
    waktu_sekarang = datetime.now().time()

    # Dapatkan waktu batas absensi dari pengaturan (digunakan untuk siswa dan pegawai Guru & Staf)
    setting = SettingWaktu.query.first()
    # Asumsi waktu batas absensi berlaku sama untuk penentuan Alfa/Tidak Tercatat
    waktu_batas_absen_masuk = setting.jam_terlambat_selesai if setting and setting.jam_terlambat_selesai else time(8, 0,
                                                                                                                   0)

    # --- 1. PERHITUNGAN ABSENSI SISWA (MENGGUNAKAN MODEL ABSENSI) ---

    # Hitung total siswa dan kelas
    total_siswa = Siswa.query.count()
    total_kelas = Kelas.query.count()

    # Kumpulkan NIS berdasarkan status absensi hari ini
    nis_hadir_terlambat = [
        absensi.nis for absensi in Absensi.query.filter(
            Absensi.tanggal == hari_ini,
            Absensi.jenis_absen == "masuk",
            Absensi.status.in_(["Hadir", "Terlambat"])
        ).distinct(Absensi.nis).all()
    ]

    nis_sakit_izin = [
        absensi.nis for absensi in Absensi.query.filter(
            Absensi.tanggal == hari_ini,
            Absensi.status.in_(["Sakit", "Izin"])
        ).distinct(Absensi.nis).all()
    ]

    # Gabungkan dan hitung siswa yang sudah tercatat
    semua_nis_tercatat = set(nis_hadir_terlambat + nis_sakit_izin)
    siswa_berstatus = len(semua_nis_tercatat)

    # Hitung jumlah untuk setiap status siswa
    total_terlambat_siswa = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Terlambat",
        Absensi.jenis_absen == "masuk"
    ).distinct(Absensi.nis).count()

    total_hadir_tepat_siswa = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Hadir",
        Absensi.jenis_absen == "masuk"
    ).distinct(Absensi.nis).count()

    total_sakit_siswa = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Sakit"
    ).distinct(Absensi.nis).count()

    total_izin_siswa = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Izin"
    ).distinct(Absensi.nis).count()

    # Hitung total alfa siswa berdasarkan waktu batas
    if waktu_sekarang > waktu_batas_absen_masuk:
        total_alfa_siswa = total_siswa - siswa_berstatus
    else:
        total_alfa_siswa = 0

    # --- 2. PERHITUNGAN ABSENSI PEGAWAI (MENGGUNAKAN MODEL ABSENSIPEGAWAI) ---

    # Dapatkan ID semua pegawai
    total_pegawai = Pegawai.query.count()

    # Kumpulkan NO_ID pegawai yang sudah tercatat HARI INI (Hadir/Terlambat/Sakit/Izin)
    pegawai_hadir_terlambat_ids = [
        absensi.no_id for absensi in AbsensiPegawai.query.filter(
            AbsensiPegawai.tanggal == hari_ini,
            AbsensiPegawai.jenis_absen == "masuk",
            AbsensiPegawai.status.in_(["Hadir", "Terlambat"])
        ).distinct(AbsensiPegawai.no_id).all()
    ]

    pegawai_sakit_izin_ids = [
        absensi.no_id for absensi in AbsensiPegawai.query.filter(
            AbsensiPegawai.tanggal == hari_ini,
            AbsensiPegawai.status.in_(["Sakit", "Izin"])
        ).distinct(AbsensiPegawai.no_id).all()
    ]

    # Gabungkan semua pegawai yang sudah punya status hari ini
    semua_pegawai_tercatat = set(pegawai_hadir_terlambat_ids + pegawai_sakit_izin_ids)
    pegawai_berstatus = len(semua_pegawai_tercatat)

    # Hitung jumlah untuk setiap status pegawai
    total_terlambat_pegawai = AbsensiPegawai.query.filter(
        AbsensiPegawai.tanggal == hari_ini,
        AbsensiPegawai.status == "Terlambat",
        AbsensiPegawai.jenis_absen == "masuk"
    ).distinct(AbsensiPegawai.no_id).count()

    total_hadir_tepat_pegawai = AbsensiPegawai.query.filter(
        AbsensiPegawai.tanggal == hari_ini,
        AbsensiPegawai.status == "Hadir",
        AbsensiPegawai.jenis_absen == "masuk"
    ).distinct(AbsensiPegawai.no_id).count()

    total_sakit_pegawai = AbsensiPegawai.query.filter(
        AbsensiPegawai.tanggal == hari_ini,
        AbsensiPegawai.status == "Sakit"
    ).distinct(AbsensiPegawai.no_id).count()

    total_izin_pegawai = AbsensiPegawai.query.filter(
        AbsensiPegawai.tanggal == hari_ini,
        AbsensiPegawai.status == "Izin"
    ).distinct(AbsensiPegawai.no_id).count()

    # Hitung total tidak tercatat (Alfa) pegawai
    if waktu_sekarang > waktu_batas_absen_masuk:
        # Jika sudah lewat batas waktu, hitung yang belum absen
        total_tidak_tercatat_pegawai = total_pegawai - pegawai_berstatus
    else:
        # Jika belum lewat batas waktu, dianggap 0
        total_tidak_tercatat_pegawai = 0

    # Tampilkan data ke template
    return render_template(
        "dashboard.html",
        # Data Siswa
        total_hadir_siswa=total_hadir_tepat_siswa,
        total_terlambat_siswa=total_terlambat_siswa,
        total_sakit_siswa=total_sakit_siswa,
        total_izin_siswa=total_izin_siswa,
        total_alfa_siswa=total_alfa_siswa,
        total_siswa=total_siswa,
        total_kelas=total_kelas,

        # Data Pegawai (BARU)
        total_hadir_pegawai=total_hadir_tepat_pegawai,
        total_terlambat_pegawai=total_terlambat_pegawai,
        total_sakit_pegawai=total_sakit_pegawai,
        total_izin_pegawai=total_izin_pegawai,
        total_pegawai=total_pegawai,
        total_tidak_tercatat_pegawai=total_tidak_tercatat_pegawai,
    )