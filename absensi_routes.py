import calendar
from flask import Blueprint, request, render_template, flash, redirect, url_for
from utils import check_admin_session
from datetime import datetime
from models import Kelas, Siswa, Absensi, db, HariLibur, SettingWaktu

# Inisialisasi Blueprint dengan prefix URL
absensi_bp = Blueprint("absensi_bp", __name__, url_prefix="/absensi")

# =======================================================================
#  ROUTE: KELOLA DATA ABSENSI (DENGAN INTEGRASI HARI LIBUR)
# =======================================================================
@absensi_bp.route("/", methods=["GET"])
def absensi():
    """Tampilkan data absensi harian dengan filter kelas, nama, dan status."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Ambil tanggal dari parameter URL, atau default ke hari ini
    tanggal_str = request.args.get('tanggal', datetime.today().strftime('%Y-%m-%d'))
    try:
        tanggal_obj = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
    except ValueError:
        tanggal_obj = datetime.today().date()

    nama_hari_en = calendar.day_name[tanggal_obj.weekday()]
    daftar_hari_id = {
        'Monday': 'Senin', 'Tuesday': 'Selasa', 'Wednesday': 'Rabu',
        'Thursday': 'Kamis', 'Friday': 'Jumat', 'Saturday': 'Sabtu', 'Sunday': 'Minggu'
    }
    nama_hari_id = daftar_hari_id.get(nama_hari_en, nama_hari_en)

    info_hari = None

    # ==============================================================================
    #  INTEGRASI: Lakukan Pengecekan Hari Libur Berlapis
    # ==============================================================================
    setting = SettingWaktu.query.first()
    if setting and setting.hari_libur_rutin:
        if nama_hari_id in setting.hari_libur_rutin.split(','):
            info_hari = f"Tanggal {tanggal_obj.strftime('%d %B %Y')} adalah hari libur rutin ({nama_hari_id})."
    
    if not info_hari:
        libur_spesial = HariLibur.query.filter_by(tanggal=tanggal_obj).first()
        if libur_spesial:
            info_hari = f"Tanggal {tanggal_obj.strftime('%d %B %Y')} adalah hari libur: {libur_spesial.keterangan}."
    
    data_absensi_terurut = []
    if not info_hari:
        # --- FITUR ASLI: Jalankan logika pengambilan data jika bukan hari libur ---
        kelas_id = request.args.get("kelas_id")
        cari_nama = request.args.get("cari_nama")
        status_filter = request.args.get("status")
        
        siswa_query = Siswa.query.join(Kelas)
        if cari_nama:
            siswa_query = siswa_query.filter(Siswa.nama.ilike(f"%{cari_nama}%"))
        if kelas_id:
            siswa_query = siswa_query.filter(Siswa.kelas_id == kelas_id)

        semua_siswa = siswa_query.order_by(Siswa.nama.asc()).all()
        absensi_hari_ini = Absensi.query.filter(Absensi.tanggal == tanggal_obj).all()

        absensi_dict = {}
        for absen in absensi_hari_ini:
            if absen.nis not in absensi_dict:
                absensi_dict[absen.nis] = {'masuk': None, 'pulang': None}
            if absen.jenis_absen == 'masuk':
                absensi_dict[absen.nis]['masuk'] = absen
            elif absen.jenis_absen == 'pulang':
                absensi_dict[absen.nis]['pulang'] = absen
            elif absen.jenis_absen == 'lainnya':
                absensi_dict[absen.nis]['masuk'] = absen
                absensi_dict[absen.nis]['pulang'] = absen

        data_absensi = []
        for siswa in semua_siswa:
            data_siswa = {
                "siswa": siswa,
                "masuk": absensi_dict.get(siswa.nis, {}).get('masuk'),
                "pulang": absensi_dict.get(siswa.nis, {}).get('pulang')
            }

            if status_filter:
                siswa_status = data_siswa['masuk'].status if data_siswa['masuk'] else 'Alfa'
                if siswa_status == status_filter or (status_filter == 'Alfa' and not data_siswa['masuk']):
                    data_absensi.append(data_siswa)
            else:
                data_absensi.append(data_siswa)

        data_absensi_terurut = sorted(
            data_absensi,
            key=lambda item: (item['masuk'] is None, item['masuk'].waktu if item['masuk'] else None)
        )
    
    kelas_list = Kelas.query.order_by(Kelas.nama.asc()).all()
    return render_template(
        "absensi.html",
        data_absensi=data_absensi_terurut,
        kelas_list=kelas_list,
        kelas_id=request.args.get("kelas_id"),
        cari_nama=request.args.get("cari_nama"),
        status=request.args.get("status"),
        info_hari=info_hari, # Kirim info hari libur ke template
        tanggal_dipilih=tanggal_obj
    )

# =======================================================================
#  FILTER WARNA BADGE (Tidak Berubah)
# =======================================================================
def get_badge_color(status):
    """Warna badge Bootstrap berdasarkan status absensi."""
    return (
        'success' if status in ['masuk', 'pulang', 'Hadir'] else
        'warning' if status == 'Sakit' else
        'primary' if status == 'Izin' else
        'danger' if status == 'Alfa' else
        'secondary'
    )

# =======================================================================
#  ROUTE: UPDATE STATUS ABSENSI (Tidak Berubah)
# =======================================================================
@absensi_bp.route("/update/<string:nis>", methods=["POST"])
def update_absensi(nis):
    """Perbarui status absensi siswa."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    status = request.form.get("status")
    kelas_id = request.form.get("kelas")
    cari_nama = request.form.get("cari_nama")
    tanggal = datetime.today().date()

    if not status or not nis:
        flash("Status atau NIS tidak valid.", "danger")
        return redirect(url_for("absensi_bp.absensi", kelas_id=kelas_id, cari_nama=cari_nama))

    try:
        Absensi.query.filter_by(nis=nis, tanggal=tanggal).delete()

        if status == 'Hadir':
            absen_masuk = Absensi(
                nis=nis, tanggal=tanggal, status="Hadir", jenis_absen="masuk",
                keterangan="Konfirmasi Hadir", waktu=datetime.now().time()
            )
            absen_pulang = Absensi(
                nis=nis, tanggal=tanggal, status="Hadir", jenis_absen="pulang",
                keterangan="Konfirmasi Pulang", waktu=datetime.now().time()
            )
            db.session.add_all([absen_masuk, absen_pulang])

        elif status in ['Sakit', 'Izin', 'Alfa']:
            absen_lainnya = Absensi(
                nis=nis, tanggal=tanggal, status=status, jenis_absen="lainnya",
                keterangan=status, waktu=datetime.now().time()
            )
            db.session.add(absen_lainnya)

        db.session.commit()
        flash(f"Status absensi NIS {nis} diperbarui menjadi {status}.", "success")

    except Exception as e:
        db.session.rollback()
        print(f"Error update absensi: {e}")
        flash("Terjadi kesalahan. Silakan coba lagi.", "danger")

    return redirect(url_for("absensi_bp.absensi", kelas_id=kelas_id, cari_nama=cari_nama))