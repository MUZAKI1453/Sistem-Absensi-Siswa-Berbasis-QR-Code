import calendar
from datetime import datetime
from flask import Blueprint, render_template, redirect, flash, url_for, request
from models import Pegawai, AbsensiPegawai, db, HariLibur, SettingWaktu
from utils import check_admin_session

# Inisialisasi Blueprint
absensi_pegawai_bp = Blueprint("absensi_pegawai_bp", __name__, url_prefix="/absensi_pegawai")


# =======================================================================
#  ROUTE: KELOLA DATA ABSENSI PEGAWAI (DENGAN INTEGRASI HARI LIBUR)
# =======================================================================
@absensi_pegawai_bp.route("/", methods=["GET"])
def absensi_pegawai():
    """Tampilkan data absensi harian pegawai dengan filter nama dan role."""
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
        role_filter = request.args.get("role_filter")
        cari_nama = request.args.get("cari_nama")
        status_filter = request.args.get("status")

        pegawai_query = Pegawai.query
        if cari_nama:
            pegawai_query = pegawai_query.filter(Pegawai.nama.ilike(f"%{cari_nama}%"))
        if role_filter:
            pegawai_query = pegawai_query.filter(Pegawai.role == role_filter)

        semua_pegawai = pegawai_query.order_by(Pegawai.nama.asc()).all()
        absensi_hari_ini = AbsensiPegawai.query.filter(AbsensiPegawai.tanggal == tanggal_obj).all()

        absensi_dict = {}
        for absen in absensi_hari_ini:
            if absen.no_id not in absensi_dict:
                absensi_dict[absen.no_id] = {'masuk': None, 'pulang': None}
            if absen.jenis_absen == 'masuk':
                absensi_dict[absen.no_id]['masuk'] = absen
            elif absen.jenis_absen == 'pulang':
                absensi_dict[absen.no_id]['pulang'] = absen
            elif absen.jenis_absen == 'lainnya':
                absensi_dict[absen.no_id]['masuk'] = absen
                absensi_dict[absen.no_id]['pulang'] = absen

        data_absensi = []
        for pegawai in semua_pegawai:
            data_pegawai = {
                "pegawai": pegawai,
                "masuk": absensi_dict.get(pegawai.no_id, {}).get('masuk'),
                "pulang": absensi_dict.get(pegawai.no_id, {}).get('pulang')
            }
            if status_filter:
                pegawai_status = data_pegawai['masuk'].status if data_pegawai['masuk'] else 'Alfa'
                if pegawai_status == status_filter or (status_filter == 'Alfa' and not data_pegawai['masuk']):
                    data_absensi.append(data_pegawai)
            else:
                data_absensi.append(data_pegawai)

        data_absensi_terurut = sorted(
            data_absensi,
            key=lambda item: (item['masuk'] is None, item['masuk'].waktu if item['masuk'] else None)
        )

    return render_template(
        "absensi_pegawai.html",
        data_absensi=data_absensi_terurut,
        role_filter=request.args.get("role_filter"),
        cari_nama=request.args.get("cari_nama"),
        status=request.args.get("status"),
        info_hari=info_hari,  # Kirim info hari libur ke template
        tanggal_dipilih=tanggal_obj
    )


# =======================================================================
#  FILTER UNTUK WARNA BADGE STATUS (Tidak Berubah)
# =======================================================================
def get_badge_color(status):
    """Tentukan kelas Bootstrap untuk warna badge berdasarkan status absensi."""
    return (
        'success' if status in ['masuk', 'pulang', 'Hadir']
        else 'warning' if status == 'Sakit'
        else 'primary' if status == 'Izin'
        else 'danger' if status == 'Alfa'
        else 'secondary'
    )


# Daftarkan filter ke Jinja (saat app aktif)
@absensi_pegawai_bp.record_once
def register_filters(state):
    state.app.jinja_env.filters['get_badge_color'] = get_badge_color


# =======================================================================
#  ROUTE: UPDATE STATUS ABSENSI PEGAWAI (Tidak Berubah)
# =======================================================================
@absensi_pegawai_bp.route("/update/<string:no_id>", methods=["POST"])
def update_absensi_pegawai(no_id):
    """Perbarui status absensi pegawai (Hadir, Sakit, Izin, Alfa)."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    status = request.form.get("status")
    role_filter = request.form.get("role_filter")
    cari_nama = request.form.get("cari_nama")
    tanggal = datetime.today().date()

    if not status or not no_id:
        flash("Status atau No ID tidak valid.", "danger")
        return redirect(url_for("absensi_pegawai_bp.absensi_pegawai", role_filter=role_filter, cari_nama=cari_nama))

    try:
        # Hapus semua entri absensi untuk hari ini
        AbsensiPegawai.query.filter_by(no_id=no_id, tanggal=tanggal).delete()

        # Tentukan jenis absen berdasarkan status
        if status == 'Hadir':
            absen_masuk = AbsensiPegawai(
                no_id=no_id,
                tanggal=tanggal,
                status="Hadir",
                jenis_absen="masuk",
                keterangan="Konfirmasi Hadir",
                waktu=datetime.now().time()
            )
            absen_pulang = AbsensiPegawai(
                no_id=no_id,
                tanggal=tanggal,
                status="Hadir",
                jenis_absen="pulang",
                keterangan="Konfirmasi Pulang",
                waktu=datetime.now().time()
            )
            db.session.add(absen_masuk)
            db.session.add(absen_pulang)
        elif status in ['Sakit', 'Izin', 'Alfa']:
            absen_lainnya = AbsensiPegawai(
                no_id=no_id,
                tanggal=tanggal,
                status=status,
                jenis_absen="lainnya",
                keterangan=status,
                waktu=datetime.now().time()
            )
            db.session.add(absen_lainnya)

        db.session.commit()
        flash(f"Status absensi No ID {no_id} diperbarui menjadi {status}.", "success")

    except Exception as e:
        db.session.rollback()
        print(f"Error update absensi pegawai: {e}")
        flash("Terjadi kesalahan. Silakan coba lagi.", "danger")

    return redirect(url_for("absensi_pegawai_bp.absensi_pegawai", role_filter=role_filter, cari_nama=cari_nama))


# =======================================================================
#  ROUTE BARU: UBAH STATUS ABSENSI PEGAWAI SECARA MASAL
# =======================================================================
@absensi_pegawai_bp.route("/update_status_masal", methods=["POST"])
def update_status_masal():
    """Perbarui status absensi banyak pegawai secara masal untuk tanggal yang dipilih."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    no_id_list = request.form.getlist("no_id_list")  # Ambil list ID yang diceklis
    status = request.form.get("status_masal")  # Ambil status baru
    tanggal_str = request.form.get("tanggal_dipilih")  # Ambil tanggal yang sedang dilihat

    if not no_id_list or not status or not tanggal_str:
        flash("Input tidak valid. Pastikan Anda memilih setidaknya satu pegawai dan status.", "danger")
        # Redirect ke halaman utama dengan filter tanggal yang sama
        return redirect(
            url_for("absensi_pegawai_bp.absensi_pegawai", tanggal=tanggal_str or datetime.today().strftime('%Y-%m-%d')))

    try:
        tanggal_obj = datetime.strptime(tanggal_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Format tanggal tidak valid.", "danger")
        return redirect(url_for("absensi_pegawai_bp.absensi_pegawai"))

    try:
        updated_count = 0
        now_time = datetime.now().time()

        for no_id in no_id_list:
            # 1. Hapus semua entri absensi untuk hari ini (masuk, pulang, atau lainnya)
            AbsensiPegawai.query.filter_by(no_id=no_id, tanggal=tanggal_obj).delete()

            # 2. Tambahkan entri baru berdasarkan status
            if status == 'Hadir':
                # Absensi Masuk (Hadir)
                absen_masuk = AbsensiPegawai(
                    no_id=no_id,
                    tanggal=tanggal_obj,
                    status="Hadir",
                    jenis_absen="masuk",
                    keterangan="Konfirmasi Hadir Masal",
                    waktu=now_time
                )
                db.session.add(absen_masuk)

                # Absensi Pulang (Hadir)
                absen_pulang = AbsensiPegawai(
                    no_id=no_id,
                    tanggal=tanggal_obj,
                    status="Hadir",
                    jenis_absen="pulang",
                    keterangan="Konfirmasi Pulang Masal",
                    waktu=now_time
                )
                db.session.add(absen_pulang)

            elif status in ['Sakit', 'Izin', 'Alfa']:
                # Absensi Lainnya
                absen_lainnya = AbsensiPegawai(
                    no_id=no_id,
                    tanggal=tanggal_obj,
                    status=status,
                    jenis_absen="lainnya",
                    keterangan=f"Konfirmasi Masal: {status}",
                    waktu=now_time
                )
                db.session.add(absen_lainnya)

            updated_count += 1

        db.session.commit()
        flash(
            f"Berhasil memperbarui status {updated_count} pegawai menjadi '{status}' untuk tanggal {tanggal_obj.strftime('%d %B %Y')}.",
            "success")

    except Exception as e:
        db.session.rollback()
        print(f"Error update absensi pegawai masal: {e}")
        flash("Terjadi kesalahan saat pembaruan masal. Silakan coba lagi.", "danger")

    # Redirect kembali ke halaman utama dengan tanggal yang dipilih
    return redirect(url_for("absensi_pegawai_bp.absensi_pegawai", tanggal=tanggal_str))