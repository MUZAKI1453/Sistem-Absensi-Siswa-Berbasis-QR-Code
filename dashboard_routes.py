import calendar
from datetime import datetime, time
from flask import Blueprint, render_template
from models import SettingWaktu, Siswa, Kelas, Absensi, Pegawai, AbsensiPegawai, HariLibur
from utils import check_admin_session

dashboard_bp = Blueprint("dashboard_bp", __name__, url_prefix="/dashboard")

# =======================================================================
#  ROUTE: DASHBOARD UTAMA (DENGAN INTEGRASI HARI LIBUR & LOGIKA LENGKAP)
# =======================================================================
@dashboard_bp.route("/")
def dashboard():
    """Tampilkan dashboard dengan statistik absensi hari ini."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # --- Variabel Global ---
    hari_ini = datetime.today().date()
    nama_hari_ini_en = calendar.day_name[hari_ini.weekday()]
    
    # Konversi nama hari ke Bahasa Indonesia
    daftar_hari_id = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    nama_hari_ini_id = daftar_hari_id.get(nama_hari_ini_en, nama_hari_ini_en)
    
    info_hari_ini = None # Variabel untuk pesan libur

    # ==============================================================================
    #  INTEGRASI: Lakukan Pengecekan Hari Libur Berlapis
    # ==============================================================================
    setting_waktu = SettingWaktu.query.first()
    
    # 1. Cek Libur Rutin (Mingguan)
    if setting_waktu and setting_waktu.hari_libur_rutin:
        libur_rutin = setting_waktu.hari_libur_rutin.split(',')
        if nama_hari_ini_id in libur_rutin:
            info_hari_ini = f"Hari {nama_hari_ini_id} adalah hari libur rutin."

    # 2. Cek Libur Spesial (Tanggal Merah), jika bukan libur rutin
    if not info_hari_ini:
        libur_spesial = HariLibur.query.filter_by(tanggal=hari_ini).first()
        if libur_spesial:
            info_hari_ini = f"Hari ini libur: {libur_spesial.keterangan}."

    # ==============================================================================
    #  LOGIKA PERHITUNGAN STATISTIK
    # ==============================================================================

    # Jika hari ini libur, set semua statistik ke 0
    if info_hari_ini:
        total_hadir_tepat_siswa = 0
        total_terlambat_siswa = 0
        total_sakit_siswa = 0
        total_izin_siswa = 0
        total_alfa_siswa = 0
        total_hadir_tepat_pegawai = 0
        total_terlambat_pegawai = 0
        total_sakit_pegawai = 0
        total_izin_pegawai = 0
        total_tidak_tercatat_pegawai = 0
    else:
        # --- KODE ASLI ANDA DIKEMBALIKAN SEPENUHNYA ---
        waktu_sekarang = datetime.now().time()
        waktu_batas_absen_masuk = setting_waktu.jam_terlambat_selesai if setting_waktu and setting_waktu.jam_terlambat_selesai else time(8, 0, 0)
        total_siswa = Siswa.query.count()

        # --- 1. PERHITUNGAN ABSENSI SISWA (LOGIKA ASLI ANDA) ---
        nis_hadir_terlambat = [absensi.nis for absensi in Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.jenis_absen == "masuk", Absensi.status.in_(["Hadir", "Terlambat"])).distinct(Absensi.nis).all()]
        nis_sakit_izin = [absensi.nis for absensi in Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.status.in_(["Sakit", "Izin"])).distinct(Absensi.nis).all()]
        
        semua_nis_tercatat = set(nis_hadir_terlambat + nis_sakit_izin)
        siswa_berstatus = len(semua_nis_tercatat)

        total_terlambat_siswa = Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.status == "Terlambat", Absensi.jenis_absen == "masuk").distinct(Absensi.nis).count()
        total_hadir_tepat_siswa = Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.status == "Hadir", Absensi.jenis_absen == "masuk").distinct(Absensi.nis).count()
        total_sakit_siswa = Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.status == "Sakit").distinct(Absensi.nis).count()
        total_izin_siswa = Absensi.query.filter(Absensi.tanggal == hari_ini, Absensi.status == "Izin").distinct(Absensi.nis).count()

        if waktu_sekarang > waktu_batas_absen_masuk:
            total_alfa_siswa = total_siswa - siswa_berstatus
        else:
            total_alfa_siswa = 0

        # --- 2. PERHITUNGAN ABSENSI PEGAWAI (LOGIKA ASLI ANDA) ---
        total_pegawai = Pegawai.query.count()
        
        pegawai_hadir_terlambat_ids = [absensi.no_id for absensi in AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.jenis_absen == "masuk", AbsensiPegawai.status.in_(["Hadir", "Terlambat"])).distinct(AbsensiPegawai.no_id).all()]
        pegawai_sakit_izin_ids = [absensi.no_id for absensi in AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.status.in_(["Sakit", "Izin"])).distinct(AbsensiPegawai.no_id).all()]

        semua_pegawai_tercatat = set(pegawai_hadir_terlambat_ids + pegawai_sakit_izin_ids)
        pegawai_berstatus = len(semua_pegawai_tercatat)

        total_terlambat_pegawai = AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.status == "Terlambat", AbsensiPegawai.jenis_absen == "masuk").distinct(AbsensiPegawai.no_id).count()
        total_hadir_tepat_pegawai = AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.status == "Hadir", AbsensiPegawai.jenis_absen == "masuk").distinct(AbsensiPegawai.no_id).count()
        total_sakit_pegawai = AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.status == "Sakit").distinct(AbsensiPegawai.no_id).count()
        total_izin_pegawai = AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == hari_ini, AbsensiPegawai.status == "Izin").distinct(AbsensiPegawai.no_id).count()

        if waktu_sekarang > waktu_batas_absen_masuk:
            total_tidak_tercatat_pegawai = total_pegawai - pegawai_berstatus
        else:
            total_tidak_tercatat_pegawai = 0

    # Ambil total global (selalu dihitung di luar kondisi)
    total_siswa = Siswa.query.count()
    total_kelas = Kelas.query.count()
    total_pegawai = Pegawai.query.count()

    return render_template(
        "dashboard.html",
        # Data Siswa
        total_hadir_siswa=total_hadir_tepat_siswa,
        total_terlambat_siswa=total_terlambat_siswa,
        total_sakit_siswa=total_sakit_siswa,
        total_izin_siswa=total_izin_siswa,
        total_alfa_siswa=max(0, total_alfa_siswa), 
        total_siswa=total_siswa,
        total_kelas=total_kelas,
        # Data Pegawai
        total_hadir_pegawai=total_hadir_tepat_pegawai,
        total_terlambat_pegawai=total_terlambat_pegawai,
        total_sakit_pegawai=total_sakit_pegawai,
        total_izin_pegawai=total_izin_pegawai,
        total_pegawai=total_pegawai,
        total_tidak_tercatat_pegawai=max(0, total_tidak_tercatat_pegawai), 
        # Info Hari Ini (BARU)
        info_hari_ini=info_hari_ini
    )