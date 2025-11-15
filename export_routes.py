# Import standard library modules first
import calendar
import io
from datetime import date, datetime

# Import third-party modules
import pandas as pd
from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

# Import local application modules
from models import (
    Absensi, AbsensiPegawai, HariLibur, JadwalKeamanan, Kelas, Pegawai,
    SettingWaktu, SettingWaktuGuruStaf, SettingWaktuKeamanan, Siswa, db
)
from utils import check_admin_session

# Inisialisasi Blueprint
export_bp = Blueprint("export_bp", __name__, url_prefix="/export")


@export_bp.route("/", methods=["GET", "POST"])
def export_laporan():
    """Menampilkan halaman ekspor dan menangani pengiriman form."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    if request.method == "POST":
        # Redirect ke fungsi download dengan parameter dari form
        return redirect(url_for("export_bp.download_laporan", **request.form))

    # Mengambil semua data yang diperlukan untuk mengisi dropdown di frontend
    tipe_filter = request.args.get('tipe')
    semua_kelas = Kelas.query.order_by(Kelas.nama.asc()).all()
    semua_siswa = Siswa.query.order_by(Siswa.nama.asc()).all()
    semua_pegawai = Pegawai.query.order_by(Pegawai.nama.asc()).all()

    return render_template(
        "export_laporan.html",
        current_year=datetime.now().year,
        tipe_filter=tipe_filter,
        semua_kelas=semua_kelas,
        semua_siswa=semua_siswa,
        semua_pegawai=semua_pegawai
    )


def _get_time_difference(start_time, end_time):
    """Menghitung perbedaan total waktu dalam format jam dan menit."""
    if not start_time or not end_time:
        return '-'
    try:
        total_detik = (datetime.combine(date.today(), end_time) - datetime.combine(date.today(),
                                                                                   start_time)).total_seconds()
        if total_detik < 0:
            return 'Error (Waktu Keluar Sebelum Masuk)'

        jam, sisa = divmod(total_detik, 3600)
        menit, _ = divmod(sisa, 60)
        return f"{int(jam)} jam {int(menit)} menit"
    except (TypeError, ValueError):
        return "Error"


def _get_late_time(check_in_time, deadline):
    """Menghitung waktu keterlambatan dalam menit."""
    if not check_in_time or not deadline:
        return '-'
    try:
        terlambat_detik = (
                datetime.combine(date.today(), check_in_time) - datetime.combine(date.today(), deadline)
        ).total_seconds()
        if terlambat_detik > 0:
            menit, _ = divmod(terlambat_detik, 60)
            return f"{int(menit)} menit"
        return '-'
    except (TypeError, ValueError):
        return "Error"


def _get_deadline_for_person(tipe_data, orang, tanggal, setting_siswa, setting_pegawai_umum, pengaturan_shift_keamanan,
                             jadwal_keamanan_dict):
    """Menentukan batas waktu absensi (deadline) berdasarkan role/shift."""
    deadline = None
    if tipe_data == 'siswa' and setting_siswa:
        deadline = setting_siswa.jam_masuk_selesai
    elif tipe_data == 'pegawai':
        if orang.role in ('guru', 'staf') and setting_pegawai_umum:
            deadline = setting_pegawai_umum.jam_masuk_selesai
        elif orang.role == 'keamanan':
            # Jika laporan grup, jadwal_keamanan_dict adalah dict of dicts, harus pakai get(orang.id)
            if isinstance(jadwal_keamanan_dict, dict) and orang.id in jadwal_keamanan_dict:
                shift = jadwal_keamanan_dict.get(orang.id).get(tanggal)
            # Jika laporan individu, jadwal_keamanan_dict adalah dict of dates
            elif isinstance(jadwal_keamanan_dict, dict):
                shift = jadwal_keamanan_dict.get(tanggal)
            else:
                shift = None

            if shift in pengaturan_shift_keamanan:
                deadline = pengaturan_shift_keamanan[shift].jam_masuk_selesai
    return deadline


@export_bp.route("/download_laporan")
def download_laporan():
    """Memproses dan menghasilkan file laporan berdasarkan parameter."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Mengambil semua parameter dari URL
    tipe_data = request.args.get("tipe_data")
    jenis_laporan = request.args.get("jenis_laporan")
    format_file = request.args.get("format_file")

    tanggal_str = request.args.get("tanggal")
    bulan = request.args.get("bulan")
    tahun = request.args.get("tahun")
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    data = []
    df = pd.DataFrame()
    filename = f"laporan_{tipe_data}"
    sheet_name = "Laporan"

    # ===================================================================
    # BLOCK UTAMA: Logika berbeda untuk setiap jenis laporan
    # ===================================================================

    if jenis_laporan == 'individu':
        # --- LOGIKA UNTUK LAPORAN PER INDIVIDU ---
        if tipe_data == 'siswa':
            individu_id = request.args.get("individu_id_siswa")
            ModelOrang, ModelAbsensi, id_field = Siswa, Absensi, 'nis'
        else:
            individu_id = request.args.get("individu_id_pegawai")
            ModelOrang, ModelAbsensi, id_field = Pegawai, AbsensiPegawai, 'no_id'

        if not individu_id:
            flash("Silakan pilih nama individu untuk laporan.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        if not bulan or not tahun:
            flash("Silakan pilih bulan dan tahun untuk laporan individu.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        # Penentuan Tanggal Mulai dan Akhir
        try:
            int_tahun, int_bulan = int(tahun), int(bulan)
            start_dt = date(int_tahun, int_bulan, 1)
            end_dt = date(int_tahun, int_bulan, calendar.monthrange(int_tahun, int_bulan)[1])
            month_name = calendar.month_name[int_bulan]
        except ValueError:
            flash("Format Bulan/Tahun tidak valid.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        orang = db.session.query(ModelOrang).filter(getattr(ModelOrang, id_field) == individu_id).first()
        if not orang:
            flash("Data individu tidak ditemukan.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        sheet_name = f"Absensi {orang.nama}"
        filename += f"_individu_{orang.nama.replace(' ', '_')}_{month_name}_{tahun}"

        # Ambil semua data absensi dalam rentang bulan
        absensi_records = db.session.query(ModelAbsensi).filter(
            getattr(ModelAbsensi, id_field) == individu_id,
            ModelAbsensi.tanggal.between(start_dt, end_dt)
        ).all()

        # Pemetaan Absensi Harian untuk kemudahan akses
        absensi_harian = {}
        for absen in absensi_records:
            tgl = absen.tanggal
            if tgl not in absensi_harian:
                absensi_harian[tgl] = {'masuk': None, 'pulang': None, 'status': 'Alfa'}

            if absen.jenis_absen == 'masuk':
                absensi_harian[tgl]['masuk'] = absen.waktu
                absensi_harian[tgl]['status'] = absen.status
            elif absen.jenis_absen == 'pulang':
                absensi_harian[tgl]['pulang'] = absen.waktu
            elif absen.jenis_absen == 'lainnya':
                absensi_harian[tgl]['status'] = absen.status

        # Ambil Data Pengaturan Waktu
        setting_siswa = SettingWaktu.query.first()
        setting_pegawai_umum = SettingWaktuGuruStaf.query.first()
        pengaturan_shift_keamanan = {s.nama_shift: s for s in SettingWaktuKeamanan.query.all()}

        # Ambil Jadwal Keamanan (jika pegawainya adalah keamanan)
        jadwal_keamanan_dict = {}
        if tipe_data == 'pegawai' and orang.role == 'keamanan':
            jadwal_records = JadwalKeamanan.query.filter(
                JadwalKeamanan.pegawai_id == orang.id,
                JadwalKeamanan.tanggal.between(start_dt, end_dt)
            ).all()
            jadwal_keamanan_dict = {j.tanggal: j.shift for j in jadwal_records}

        # ==============================================================================
        #  PERUBAHAN 1: Logika libur rutin untuk laporan INDIVIDU
        # ==============================================================================
        
        # Ambil Hari Libur (spesial/tanggal merah)
        holidays_set = {libur.tanggal for libur in
                        HariLibur.query.filter(HariLibur.tanggal.between(start_dt, end_dt)).all()}

        # Tentukan hari libur rutin berdasarkan tipe data (Siswa atau Pegawai)
        day_map = {'senin': 0, 'selasa': 1, 'rabu': 2, 'kamis': 3, 'jumat': 4, 'sabtu': 5, 'minggu': 6}
        libur_rutin_string = None

        if tipe_data == 'siswa':
            if setting_siswa and setting_siswa.hari_libur_rutin:
                libur_rutin_string = setting_siswa.hari_libur_rutin
        elif tipe_data == 'pegawai':
            # Gunakan setting pegawai, HANYA jika rolenya BUKAN keamanan
            if orang.role in ('guru', 'staf') and setting_pegawai_umum and setting_pegawai_umum.hari_libur_rutin:
                libur_rutin_string = setting_pegawai_umum.hari_libur_rutin

        if libur_rutin_string:
            libur_rutin_idx = {
                day_map[day.strip()] for day in libur_rutin_string.lower().split(',') if
                day.strip() in day_map
            }
            for dt in pd.date_range(start_dt, end_dt):
                if dt.weekday() in libur_rutin_idx:
                    holidays_set.add(dt.date())
        # ==============================================================================

        # Inisialisasi counter summary
        total_hadir, total_sakit, total_izin, total_alfa = 0, 0, 0, 0

        # Iterasi setiap hari dalam bulan
        for tgl in pd.date_range(start_dt, end_dt):
            tanggal = tgl.date()
            detail = absensi_harian.get(tanggal)

            status_laporan, jam_masuk, jam_pulang, waktu_terlambat, total_waktu = 'Alfa', '-', '-', '-', '-'
            is_keamanan = tipe_data == 'pegawai' and orang.role == 'keamanan'
            status_asli = detail.get('status', 'Alfa') if detail else 'Alfa'

            # Cek Libur/Off
            is_off_or_libur = False
            if is_keamanan:
                shift = jadwal_keamanan_dict.get(tanggal)
                if shift == 'Off':
                    status_laporan = 'Off'
                    is_off_or_libur = True
                # (Keamanan tidak peduli hari libur global)
            elif tanggal in holidays_set:
                status_laporan = 'Libur'
                is_off_or_libur = True

            # Jika hari kerja/masuk (bukan Libur/Off)
            if not is_off_or_libur:
                if detail:
                    jam_masuk_obj = detail.get('masuk')
                    jam_pulang_obj = detail.get('pulang')

                    status_laporan = status_asli

                    jam_masuk = jam_masuk_obj.strftime('%H:%M:%S') if jam_masuk_obj else '-'
                    jam_pulang = jam_pulang_obj.strftime('%H:%M:%S') if jam_pulang_obj else '-'

                    # Hitung Terlambat dan Total Waktu (Hanya untuk status Hadir/Terlambat)
                    if status_asli in ('Hadir', 'Terlambat'):
                        status_laporan = 'Hadir'
                        deadline = _get_deadline_for_person(
                            tipe_data, orang, tanggal, setting_siswa, setting_pegawai_umum, pengaturan_shift_keamanan,
                            jadwal_keamanan_dict
                        )

                        waktu_terlambat = _get_late_time(jam_masuk_obj, deadline)
                        total_waktu = _get_time_difference(jam_masuk_obj, jam_pulang_obj)

                    elif status_asli == 'Alfa':
                        pass

                    else:  # Sakit/Izin
                        status_laporan = status_asli

            # Inkrementasi counter summary
            if status_laporan == 'Hadir':
                total_hadir += 1
            elif status_laporan == 'Sakit':
                total_sakit += 1
            elif status_laporan == 'Izin':
                total_izin += 1
            elif status_laporan == 'Alfa':
                total_alfa += 1

            data.append({
                "Tanggal": tanggal.strftime('%d-%m-%Y'),
                "Status": status_laporan,
                "Jam Masuk": jam_masuk,
                "Jam Keluar": jam_pulang,
                "Waktu Terlambat": waktu_terlambat,
                "Total Waktu": total_waktu
            })

        df = pd.DataFrame(data)

        # Tambahkan summary DataFrame
        summary_data = [
            {'Tanggal': '', 'Status': ''},  # Baris kosong sebagai pemisah
            {'Tanggal': 'Total Hadir', 'Status': total_hadir, 'Jam Masuk': '', 'Jam Keluar': '', 'Waktu Terlambat': '',
             'Total Waktu': ''},
            {'Tanggal': 'Total Sakit', 'Status': total_sakit, 'Jam Masuk': '', 'Jam Keluar': '', 'Waktu Terlambat': '',
             'Total Waktu': ''},
            {'Tanggal': 'Total Izin', 'Status': total_izin, 'Jam Masuk': '', 'Jam Keluar': '', 'Waktu Terlambat': '',
             'Total Waktu': ''},
            {'Tanggal': 'Total Alfa', 'Status': total_alfa, 'Jam Masuk': '', 'Jam Keluar': '', 'Waktu Terlambat': '',
             'Total Waktu': ''}
        ]
        summary_df = pd.DataFrame(summary_data)
        df = pd.concat([df, summary_df], ignore_index=True).fillna('')

    else:
        # --- LOGIKA UNTUK LAPORAN GRUP (HARIAN, MINGGUAN, BULANAN) ---
        kelas_id = request.args.get("kelas_id")
        role_filter = request.args.get("role_filter")

        if tipe_data == "siswa":
            ModelOrang, ModelAbsensi = Siswa, Absensi
            id_field_orang, id_field_absensi = "nis", "nis"
            id_column_name, extra_column_name = "NIS", "Kelas"
        else:
            ModelOrang, ModelAbsensi = Pegawai, AbsensiPegawai
            id_field_orang, id_field_absensi = "no_id", "no_id"
            id_column_name, extra_column_name = "No ID", "Role"

        query_orang = ModelOrang.query
        if tipe_data == 'siswa' and kelas_id:
            query_orang = query_orang.filter(ModelOrang.kelas_id == kelas_id)
        elif tipe_data == 'pegawai' and role_filter:
            query_orang = query_orang.filter(ModelOrang.role == role_filter)

        semua_orang = query_orang.order_by(ModelOrang.nama).all()
        if not semua_orang:
            flash("Tidak ada data yang cocok dengan filter yang dipilih.", "warning")
            return redirect(url_for("export_bp.export_laporan"))

        if jenis_laporan == "harian":
            # --- LOGIKA LAPORAN HARIAN (TETAP SAMA) ---
            if not tanggal_str:
                flash("Silakan pilih tanggal untuk laporan harian.", "danger")
                return redirect(url_for("export_bp.export_laporan"))

            try:
                tanggal = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Format tanggal tidak valid.", "danger")
                return redirect(url_for("export_bp.export_laporan"))

            sheet_name = f"Laporan {tanggal}"
            filename += f"_harian_{tanggal}"

            setting_siswa = SettingWaktu.query.first()
            setting_pegawai_umum = SettingWaktuGuruStaf.query.first()
            pengaturan_shift_keamanan = {s.nama_shift: s for s in SettingWaktuKeamanan.query.all()}
            jadwal_keamanan_hari_ini = {
                j.pegawai_id: j for j in JadwalKeamanan.query.filter_by(tanggal=tanggal).all()
            }

            id_orang_terfilter = [getattr(o, id_field_orang) for o in semua_orang]

            absensi_harian = db.session.query(ModelAbsensi).filter(
                ModelAbsensi.tanggal == tanggal,
                getattr(ModelAbsensi, id_field_absensi).in_(id_orang_terfilter)
            ).all()

            absensi_per_orang = {
                getattr(o, id_field_orang): {'orang': o, 'masuk': None, 'pulang': None, 'status': 'Alfa'}
                for o in semua_orang
            }

            for absensi in absensi_harian:
                orang_id = getattr(absensi, id_field_absensi)
                if orang_id in absensi_per_orang:
                    if absensi.jenis_absen == 'masuk':
                        absensi_per_orang[orang_id]['masuk'] = absensi.waktu
                        absensi_per_orang[orang_id]['status'] = absensi.status
                    elif absensi.jenis_absen == 'pulang':
                        absensi_per_orang[orang_id]['pulang'] = absensi.waktu
                    elif absensi.jenis_absen == 'lainnya':
                        absensi_per_orang[orang_id]['status'] = absensi.status

            for orang_id, detail in absensi_per_orang.items():
                orang_obj = detail['orang']
                jam_masuk, jam_pulang = detail['masuk'], detail['pulang']
                status_asli, status_laporan = detail['status'], detail['status']
                total_waktu, waktu_terlambat = '-', '-'

                if status_asli in ('Hadir', 'Terlambat'):
                    status_laporan = 'Hadir'
                    deadline = _get_deadline_for_person(
                        tipe_data, orang_obj, tanggal, setting_siswa, setting_pegawai_umum, pengaturan_shift_keamanan,
                        jadwal_keamanan_hari_ini
                    )

                    waktu_terlambat = _get_late_time(jam_masuk, deadline)
                    total_waktu = _get_time_difference(jam_masuk, jam_pulang)

                jam_masuk_str = jam_masuk.strftime('%H:%M:%S') if jam_masuk else '-'
                jam_pulang_str = jam_pulang.strftime('%H:%M:%S') if jam_pulang else '-'

                row = {
                    id_column_name: orang_id,
                    "Nama": orang_obj.nama,
                    "Status": status_laporan,
                    "Jam Masuk": jam_masuk_str,
                    "Jam Keluar": jam_pulang_str,
                    "Waktu Terlambat": waktu_terlambat,
                    "Total Waktu": total_waktu
                }
                if tipe_data == 'siswa':
                    row[extra_column_name] = getattr(orang_obj, 'kelas_relasi', None).nama or 'N/A'
                else:
                    row[extra_column_name] = orang_obj.role
                data.append(row)

            df = pd.DataFrame(data)
            if not df.empty:
                df = df[
                    [id_column_name, "Nama", extra_column_name, "Status", "Jam Masuk", "Jam Keluar", "Waktu Terlambat",
                     "Total Waktu"]
                ]

        elif jenis_laporan == "mingguan":
            # --- LOGIKA LAPORAN MINGGUAN (FORMAT HARIAN: ROW-BY-ROW) ---
            if not start_date_str or not end_date_str:
                flash("Silakan pilih rentang tanggal untuk laporan mingguan.", "danger")
                return redirect(url_for("export_bp.export_laporan"))
            try:
                start_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Format tanggal tidak valid.", "danger")
                return redirect(url_for("export_bp.export_laporan"))

            sheet_name = f"Lap {start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b %Y')}"
            filename += f"_mingguan_detail_{start_dt}_{end_dt}"

            # 1. Ambil semua pengaturan waktu dan libur
            setting_siswa = SettingWaktu.query.first()
            setting_pegawai_umum = SettingWaktuGuruStaf.query.first()
            pengaturan_shift_keamanan = {s.nama_shift: s for s in SettingWaktuKeamanan.query.all()}

            # Ambil semua jadwal keamanan dalam rentang (untuk penentuan deadline)
            jadwal_keamanan_rentang = {}
            if tipe_data == 'pegawai':
                jadwal_records = JadwalKeamanan.query.filter(JadwalKeamanan.tanggal.between(start_dt, end_dt)).all()
                for j in jadwal_records:
                    if j.pegawai_id not in jadwal_keamanan_rentang:
                        jadwal_keamanan_rentang[j.pegawai_id] = {}
                    jadwal_keamanan_rentang[j.pegawai_id][j.tanggal] = j.shift

            # ==============================================================================
            #  PERUBAHAN 2: Logika libur rutin untuk laporan MINGGUAN
            # ==============================================================================
            
            # Ambil Hari Libur (spesial/tanggal merah)
            holidays_set = {libur.tanggal for libur in
                            HariLibur.query.filter(HariLibur.tanggal.between(start_dt, end_dt)).all()}

            # Tentukan hari libur rutin berdasarkan tipe data (Siswa atau Pegawai)
            day_map = {'senin': 0, 'selasa': 1, 'rabu': 2, 'kamis': 3, 'jumat': 4, 'sabtu': 5, 'minggu': 6}
            libur_rutin_string = None

            if tipe_data == 'siswa':
                if setting_siswa and setting_siswa.hari_libur_rutin:
                    libur_rutin_string = setting_siswa.hari_libur_rutin
            elif tipe_data == 'pegawai':
                # Untuk laporan grup, kita asumsikan libur Guru/Staf (bukan Keamanan)
                if setting_pegawai_umum and setting_pegawai_umum.hari_libur_rutin:
                    libur_rutin_string = setting_pegawai_umum.hari_libur_rutin

            if libur_rutin_string:
                libur_rutin_idx = {
                    day_map[day.strip()] for day in libur_rutin_string.lower().split(',') if
                    day.strip() in day_map
                }
                for dt in pd.date_range(start_dt, end_dt):
                    if dt.weekday() in libur_rutin_idx: holidays_set.add(dt.date())
            # ==============================================================================

            # 2. Ambil semua data absensi dalam rentang
            id_orang_terfilter = [getattr(o, id_field_orang) for o in semua_orang]
            absensi_records = db.session.query(ModelAbsensi).filter(
                getattr(ModelAbsensi, id_field_absensi).in_(id_orang_terfilter),
                ModelAbsensi.tanggal.between(start_dt, end_dt)
            ).all()

            # Strukturkan data absensi: {(orang_id, tanggal): {'masuk': time, 'pulang': time, 'status': str}}
            absensi_per_hari = {}
            for absen in absensi_records:
                key = (getattr(absen, id_field_absensi), absen.tanggal)
                if key not in absensi_per_hari:
                    absensi_per_hari[key] = {'masuk': None, 'pulang': None, 'status': 'Alfa'}

                if absen.jenis_absen == 'masuk':
                    absensi_per_hari[key]['masuk'] = absen.waktu
                    absensi_per_hari[key]['status'] = absen.status
                elif absen.jenis_absen == 'pulang':
                    absensi_per_hari[key]['pulang'] = absen.waktu
                elif absen.jenis_absen == 'lainnya':
                    absensi_per_hari[key]['status'] = absen.status

            # 3. Iterasi setiap orang dan setiap hari
            for orang in semua_orang:
                orang_id = getattr(orang, id_field_orang)
                is_keamanan = tipe_data == 'pegawai' and orang.role == 'keamanan'

                for tgl in pd.date_range(start_dt, end_dt):
                    tanggal = tgl.date()
                    key = (orang_id, tanggal)
                    detail = absensi_per_hari.get(key)

                    jam_masuk, jam_pulang = None, None
                    status_asli, status_laporan = 'Alfa', 'Alfa'
                    total_waktu, waktu_terlambat = '-', '-'

                    # Cek Libur/Off
                    is_off_or_libur = False
                    if is_keamanan:
                        shift = jadwal_keamanan_rentang.get(orang.id, {}).get(tanggal)
                        if shift == 'Off':
                            status_laporan = 'Off'
                            is_off_or_libur = True
                        # (Keamanan tidak peduli hari libur global)
                    elif tanggal in holidays_set:
                        status_laporan = 'Libur'
                        is_off_or_libur = True

                    # Jika hari kerja/masuk
                    if not is_off_or_libur and detail:
                        jam_masuk = detail.get('masuk')
                        jam_pulang = detail.get('pulang')
                        status_asli = detail.get('status', 'Alfa')
                        status_laporan = status_asli

                        if status_asli in ('Hadir', 'Terlambat'):
                            status_laporan = 'Hadir'

                            # Tentukan deadline untuk hari dan orang ini
                            deadline = _get_deadline_for_person(
                                tipe_data, orang, tanggal, setting_siswa, setting_pegawai_umum,
                                pengaturan_shift_keamanan, jadwal_keamanan_rentang
                            )

                            waktu_terlambat = _get_late_time(jam_masuk, deadline)
                            total_waktu = _get_time_difference(jam_masuk, jam_pulang)

                        elif status_asli == 'Alfa':
                            pass
                        else:  # Sakit/Izin
                            status_laporan = status_asli

                    row = {
                        "Tanggal": tanggal.strftime('%d-%m-%Y'),
                        id_column_name: orang_id,
                        "Nama": orang.nama,
                        extra_column_name: getattr(orang, 'kelas_relasi',
                                                   None).nama or 'N/A' if tipe_data == 'siswa' else orang.role,
                        "Status": status_laporan,
                        "Jam Masuk": jam_masuk.strftime('%H:%M:%S') if jam_masuk else '-',
                        "Jam Keluar": jam_pulang.strftime('%H:%M:%S') if jam_pulang else '-',
                        "Waktu Terlambat": waktu_terlambat,
                        "Total Waktu": total_waktu
                    }
                    data.append(row)

            df = pd.DataFrame(data)
            if not df.empty:
                # Kolom baru: Tanggal
                df = df[
                    ["Tanggal", id_column_name, "Nama", extra_column_name, "Status",
                     "Jam Masuk", "Jam Keluar", "Waktu Terlambat", "Total Waktu"]
                ]

        elif jenis_laporan == "bulanan":
            # --- LOGIKA LAPORAN BULANAN (TETAP DALAM FORMAT MATRIX) ---
            if not bulan or not tahun:
                flash("Silakan pilih bulan dan tahun untuk laporan bulanan.", "danger");
                return redirect(url_for("export_bp.export_laporan"))
            try:
                int_tahun, int_bulan = int(tahun), int(bulan)
                start_dt = date(int_tahun, int_bulan, 1)
                end_dt = date(int_tahun, int_bulan, calendar.monthrange(int_tahun, int_bulan)[1])
            except ValueError:
                flash("Format Bulan/Tahun tidak valid.", "danger")
                return redirect(url_for("export_bp.export_laporan"))

            sheet_name = f"Laporan {calendar.month_name[int_bulan]} {tahun}"
            filename += f"_bulanan_{bulan}_{tahun}"

            status_map = {"Hadir": "H", "Terlambat": "H", "Sakit": "S", "Izin": "I", "Alfa": "A"}
            hasil_absensi = db.session.query(ModelAbsensi).filter(ModelAbsensi.tanggal.between(start_dt, end_dt)).all()
            absensi_dict = {(getattr(absen, id_field_absensi), absen.tanggal): status_map.get(absen.status, "A") for
                            absen in hasil_absensi if absen.jenis_absen in ['masuk', 'lainnya']}

            jadwal_keamanan_dict = {}
            if tipe_data == 'pegawai':
                jadwal_records = JadwalKeamanan.query.filter(JadwalKeamanan.tanggal.between(start_dt, end_dt)).all()
                for jadwal in jadwal_records:
                    if jadwal.pegawai_id not in jadwal_keamanan_dict:
                        jadwal_keamanan_dict[jadwal.pegawai_id] = {}
                    jadwal_keamanan_dict[jadwal.pegawai_id][jadwal.tanggal] = jadwal.shift

            # ==============================================================================
            #  PERUBAHAN 3: Logika libur rutin untuk laporan BULANAN
            # ==============================================================================
            
            # Ambil Hari Libur (spesial/tanggal merah)
            holidays_set = {libur.tanggal for libur in
                            HariLibur.query.filter(HariLibur.tanggal.between(start_dt, end_dt)).all()}
            
            # Ambil kedua setting
            setting_siswa = SettingWaktu.query.first()
            setting_pegawai_umum = SettingWaktuGuruStaf.query.first()

            # Tentukan hari libur rutin berdasarkan tipe data (Siswa atau Pegawai)
            day_map = {'senin': 0, 'selasa': 1, 'rabu': 2, 'kamis': 3, 'jumat': 4, 'sabtu': 5, 'minggu': 6}
            libur_rutin_string = None
            
            if tipe_data == 'siswa':
                if setting_siswa and setting_siswa.hari_libur_rutin:
                    libur_rutin_string = setting_siswa.hari_libur_rutin
            elif tipe_data == 'pegawai':
                # Asumsikan libur Guru/Staf (bukan Keamanan)
                if setting_pegawai_umum and setting_pegawai_umum.hari_libur_rutin:
                    libur_rutin_string = setting_pegawai_umum.hari_libur_rutin

            if libur_rutin_string:
                libur_rutin_idx = {
                    day_map[day.strip()] for day in libur_rutin_string.lower().split(',') if
                    day.strip() in day_map
                }
                for dt in pd.date_range(start_dt, end_dt):
                    if dt.weekday() in libur_rutin_idx: holidays_set.add(dt.date())
            # ==============================================================================

            tanggal_range = pd.date_range(start_dt, end_dt)
            kolom_tanggal = [t.day for t in tanggal_range]

            for orang in semua_orang:
                row_data = {
                    id_column_name: getattr(orang, id_field_orang),
                    "Nama": orang.nama
                }
                is_keamanan = tipe_data == 'pegawai' and orang.role == 'keamanan'
                if tipe_data == 'siswa':
                    row_data[extra_column_name] = getattr(orang, 'kelas_relasi', None).nama or 'N/A'
                else:
                    row_data[extra_column_name] = orang.role

                total_hadir, total_sakit, total_izin, total_alfa = 0, 0, 0, 0

                for tgl_obj in tanggal_range:
                    tgl, status = tgl_obj.date(), "A"
                    orang_id_absensi = getattr(orang, id_field_orang)

                    if is_keamanan:
                        pegawai_schedule = jadwal_keamanan_dict.get(orang.id, {})
                        shift_on_day = pegawai_schedule.get(tgl)
                        if shift_on_day == 'Off':
                            status = "-"
                        elif not shift_on_day:
                            status = "A" # Jika tidak ada shift/Off, Keamanan dianggap Alfa
                        else:
                            status = absensi_dict.get((orang_id_absensi, tgl), "A")
                    else:
                        if tgl in holidays_set:
                            status = "-" # Jika Guru/Staf/Siswa libur
                        else:
                            status = absensi_dict.get((orang_id_absensi, tgl), "A")

                    if status == "H":
                        total_hadir += 1
                    elif status == "S":
                        total_sakit += 1
                    elif status == "I":
                        total_izin += 1
                    elif status == "A":
                        total_alfa += 1

                    row_data[tgl.day] = status

                row_data["Hadir"] = total_hadir
                row_data["Sakit"] = total_sakit
                row_data["Izin"] = total_izin
                row_data["Alfa"] = total_alfa
                data.append(row_data)

            df = pd.DataFrame(data)
            if not df.empty:
                kolom_total = ["Hadir", "Sakit", "Izin", "Alfa"]
                df = df[[id_column_name, "Nama", extra_column_name] + sorted(kolom_tanggal) + kolom_total]

        else:
            flash("Jenis laporan tidak valid.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

    # ============================================
    # FINALISASI DAN PEMBUATAN FILE
    # ============================================
    if df.empty:
        flash("Tidak ada data absensi yang ditemukan untuk periode dan filter yang dipilih.", "warning")
        return redirect(url_for("export_bp.export_laporan"))

    output = io.BytesIO()
    if format_file == 'csv':
        df.to_csv(output, index=False, encoding='utf-8-sig')
        mimetype, extension = 'text/csv', '.csv'
    else:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)

            workbook = writer.book
            worksheet = writer.sheets[sheet_name]

            center_format = workbook.add_format({'align': 'center', 'valign': 'vcenter'})
            left_format = workbook.add_format({'align': 'left', 'valign': 'vcenter'})
            bold_format = workbook.add_format({'bold': True, 'align': 'left', 'valign': 'vcenter'})

            # Pemformatan khusus untuk laporan individu
            if jenis_laporan == 'individu':
                if len(df) >= 5:
                    start_row_index = len(df) - 4
                    end_row_index = len(df) - 1
                    worksheet.conditional_format(f'A{start_row_index + 1}:A{end_row_index + 1}',
                                                 {'type': 'no_blanks', 'format': bold_format})

                # Pemformatan Lebar Kolom Individu
                for i, col in enumerate(df.columns):
                    if col == 'Tanggal':
                        max_len = 20
                    elif col == 'Status':
                        max_len = 10
                    else:
                        max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2

                    column_format = left_format if col in ['Tanggal'] else center_format
                    worksheet.set_column(i, i, max_len, column_format)

            elif jenis_laporan in ('harian', 'mingguan'):
                # Pemformatan Lebar Kolom Harian/Mingguan (row-by-row detail)
                for i, col in enumerate(df.columns):
                    # Adjust format alignment
                    column_format = left_format if col in ['Nama', 'Tanggal', extra_column_name] else center_format

                    # Calculate max length
                    if col == 'Tanggal':
                        max_len = 15  # Fixed width for date
                    else:
                        max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2

                    worksheet.set_column(i, i, max_len, column_format)

            else:  # Laporan Bulanan (Matrix)
                # Pemformatan Lebar Kolom Bulanan (Matrix)
                for i, col in enumerate(df.columns):
                    column_format = left_format if col in ["Nama", id_column_name, extra_column_name] else center_format
                    max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2

                    # Kolom tanggal di laporan bulanan
                    if col not in ["Nama", id_column_name, extra_column_name, "Hadir", "Sakit", "Izin", "Alfa"]:
                        max_len = 5  # Lebar kecil untuk kolom tanggal

                    worksheet.set_column(i, i, max_len, column_format)

        mimetype, extension = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'

    output.seek(0)
    return send_file(output, as_attachment=True, download_name=filename + extension, mimetype=mimetype)