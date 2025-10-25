from flask import Blueprint, render_template, request, send_file, redirect, url_for, flash
from datetime import datetime, timedelta, time, date
import pandas as pd
import io
import calendar
from utils import check_admin_session
# Import semua model yang dibutuhkan untuk logika yang kompleks
from models import (
    db, Absensi, Siswa, Pegawai, AbsensiPegawai, Kelas,
    SettingWaktu, SettingWaktuGuruStaf, HariLibur,
    JadwalKeamanan, SettingWaktuKeamanan
)

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
            ModelOrang, ModelAbsensi = Siswa, Absensi
            id_field = 'nis'
        else:
            individu_id = request.args.get("individu_id_pegawai")
            ModelOrang, ModelAbsensi = Pegawai, AbsensiPegawai
            id_field = 'no_id'

        if not individu_id:
            flash("Silakan pilih nama individu untuk laporan.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        if not bulan or not tahun:
            flash("Silakan pilih bulan dan tahun untuk laporan individu.", "danger")
            return redirect(url_for("export_bp.export_laporan"))
        
        start_dt = date(int(tahun), int(bulan), 1)
        end_dt = date(int(tahun), int(bulan), calendar.monthrange(int(tahun), int(bulan))[1])
        month_name = calendar.month_name[int(bulan)]

        orang = db.session.query(ModelOrang).filter(getattr(ModelOrang, id_field) == individu_id).first()
        if not orang:
            flash("Data individu tidak ditemukan.", "danger")
            return redirect(url_for("export_bp.export_laporan"))

        sheet_name = f"Absensi {orang.nama}"
        filename += f"_individu_{orang.nama.replace(' ','_')}_{month_name}_{tahun}"
        
        absensi_records = db.session.query(ModelAbsensi).filter(
            getattr(ModelAbsensi, id_field) == individu_id,
            ModelAbsensi.tanggal.between(start_dt, end_dt)
        ).all()
        
        absensi_harian = {absen.tanggal: {'masuk': None, 'pulang': None, 'status': 'Alfa'} for absen in absensi_records}
        for absen in absensi_records:
            if absen.jenis_absen == 'masuk':
                absensi_harian[absen.tanggal]['masuk'] = absen.waktu
                absensi_harian[absen.tanggal]['status'] = absen.status
            elif absen.jenis_absen == 'pulang':
                absensi_harian[absen.tanggal]['pulang'] = absen.waktu
            elif absen.jenis_absen == 'lainnya':
                absensi_harian[absen.tanggal]['status'] = absen.status

        setting_siswa = SettingWaktu.query.first()
        setting_pegawai_umum = SettingWaktuGuruStaf.query.first()
        pengaturan_shift_keamanan = {s.nama_shift: s for s in SettingWaktuKeamanan.query.all()}
        jadwal_keamanan_dict = {}
        if tipe_data == 'pegawai' and orang.role == 'keamanan':
            jadwal_records = JadwalKeamanan.query.filter(JadwalKeamanan.pegawai_id == orang.id, JadwalKeamanan.tanggal.between(start_dt, end_dt)).all()
            jadwal_keamanan_dict = {j.tanggal: j.shift for j in jadwal_records}

        holidays_set = {libur.tanggal for libur in HariLibur.query.filter(HariLibur.tanggal.between(start_dt, end_dt)).all()}
        if setting_siswa and setting_siswa.hari_libur_rutin:
            day_map = {'senin': 0, 'selasa': 1, 'rabu': 2, 'kamis': 3, 'jumat': 4, 'sabtu': 5, 'minggu': 6}
            libur_rutin_idx = {day_map[day.strip()] for day in setting_siswa.hari_libur_rutin.lower().split(',') if day.strip() in day_map}
            for dt in pd.date_range(start_dt, end_dt):
                if dt.weekday() in libur_rutin_idx: holidays_set.add(dt.date())

        # --- PERBAIKAN: Inisialisasi counter ---
        total_hadir, total_sakit, total_izin, total_alfa = 0, 0, 0, 0

        for tgl in pd.date_range(start_dt, end_dt):
            tanggal = tgl.date()
            detail = absensi_harian.get(tanggal)
            
            status_laporan, jam_masuk, jam_pulang, waktu_terlambat, total_waktu = 'Alfa', '-', '-', '-', '-'
            is_keamanan = tipe_data == 'pegawai' and orang.role == 'keamanan'
            
            if is_keamanan:
                shift = jadwal_keamanan_dict.get(tanggal)
                if shift == 'Off': status_laporan = 'Off'
                elif not shift: status_laporan = 'Alfa'
            elif tanggal in holidays_set:
                status_laporan = 'Libur'

            if detail and status_laporan not in ['Off', 'Libur']:
                jam_masuk_obj, jam_pulang_obj = detail.get('masuk'), detail.get('pulang')
                status_asli = detail.get('status', 'Alfa')
                status_laporan = status_asli
                jam_masuk = jam_masuk_obj.strftime('%H:%M:%S') if jam_masuk_obj else '-'
                jam_pulang = jam_pulang_obj.strftime('%H:%M:%S') if jam_pulang_obj else '-'
                
                if status_asli == 'Terlambat':
                    status_laporan = 'Hadir'
                    deadline = None
                    if tipe_data == 'siswa':
                        if setting_siswa: deadline = setting_siswa.jam_masuk_selesai
                    else:
                        if orang.role in ('guru', 'staf'):
                            if setting_pegawai_umum: deadline = setting_pegawai_umum.jam_masuk_selesai
                        elif orang.role == 'keamanan':
                            shift = jadwal_keamanan_dict.get(tanggal)
                            if shift in pengaturan_shift_keamanan:
                                deadline = pengaturan_shift_keamanan[shift].jam_masuk_selesai
                    
                    if jam_masuk_obj and deadline:
                        try:
                            terlambat_detik = (datetime.combine(date.today(), jam_masuk_obj) - datetime.combine(date.today(), deadline)).total_seconds()
                            if terlambat_detik > 0:
                                menit, _ = divmod(terlambat_detik, 60)
                                waktu_terlambat = f"{int(menit)} menit"
                        except (TypeError, ValueError): waktu_terlambat = "Error"

                if jam_masuk_obj and jam_pulang_obj and status_laporan == 'Hadir':
                    try:
                        total_detik = (datetime.combine(date.today(), jam_pulang_obj) - datetime.combine(date.today(), jam_masuk_obj)).total_seconds()
                        jam, sisa = divmod(total_detik, 3600)
                        menit, _ = divmod(sisa, 60)
                        total_waktu = f"{int(jam)} jam {int(menit)} menit"
                    except (TypeError, ValueError): total_waktu = "Error"
            
            # --- PERBAIKAN: Inkrementasi counter ---
            if status_laporan == 'Hadir': total_hadir += 1
            elif status_laporan == 'Sakit': total_sakit += 1
            elif status_laporan == 'Izin': total_izin += 1
            elif status_laporan == 'Alfa': total_alfa += 1

            data.append({
                "Tanggal": tanggal.strftime('%d-%m-%Y'), "Status": status_laporan,
                "Jam Masuk": jam_masuk, "Jam Keluar": jam_pulang,
                "Waktu Terlambat": waktu_terlambat, "Total Waktu": total_waktu
            })
        
        df = pd.DataFrame(data)
        
        # --- PERBAIKAN: Tambahkan summary DataFrame ---
        summary_data = [
            {'Tanggal': ''}, # Baris kosong sebagai pemisah
            {'Tanggal': 'Total Hadir', 'Status': total_hadir},
            {'Tanggal': 'Total Sakit', 'Status': total_sakit},
            {'Tanggal': 'Total Izin', 'Status': total_izin},
            {'Tanggal': 'Total Alfa', 'Status': total_alfa}
        ]
        summary_df = pd.DataFrame(summary_data)
        df = pd.concat([df, summary_df], ignore_index=True).fillna('')


    else:
        # --- LOGIKA UNTUK LAPORAN GRUP (HARIAN, MINGGUAN, BULANAN) ---
        # (Kode ini tetap sama seperti versi sebelumnya)
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
            if not tanggal_str:
                flash("Silakan pilih tanggal untuk laporan harian.", "danger")
                return redirect(url_for("export_bp.export_laporan"))
            
            tanggal = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            sheet_name = f"Laporan {tanggal}"
            filename += f"_harian_{tanggal}"

            setting_siswa = SettingWaktu.query.first()
            setting_pegawai_umum = SettingWaktuGuruStaf.query.first()
            pengaturan_shift_keamanan = {s.nama_shift: s for s in SettingWaktuKeamanan.query.all()}
            jadwal_keamanan_hari_ini = {j.pegawai_id: j for j in JadwalKeamanan.query.filter_by(tanggal=tanggal).all()}
            
            id_orang_terfilter = [getattr(o, id_field_orang) for o in semua_orang]
            
            absensi_harian = db.session.query(ModelAbsensi).filter(
                ModelAbsensi.tanggal == tanggal,
                getattr(ModelAbsensi, id_field_absensi).in_(id_orang_terfilter)
            ).all()
            
            absensi_per_orang = {getattr(o, id_field_orang): {'orang': o, 'masuk': None, 'pulang': None, 'status': 'Alfa'} for o in semua_orang}

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

                if status_asli == 'Terlambat':
                    status_laporan = 'Hadir'
                    deadline = None
                    
                    if tipe_data == 'siswa':
                        if setting_siswa: deadline = setting_siswa.jam_masuk_selesai
                    else: 
                        if orang_obj.role in ('guru', 'staf'):
                            if setting_pegawai_umum: deadline = setting_pegawai_umum.jam_masuk_selesai
                        elif orang_obj.role == 'keamanan':
                            jadwal = jadwal_keamanan_hari_ini.get(orang_obj.id)
                            if jadwal and jadwal.shift in pengaturan_shift_keamanan:
                                deadline = pengaturan_shift_keamanan[jadwal.shift].jam_masuk_selesai

                    if jam_masuk and deadline:
                        try:
                            terlambat_detik = (datetime.combine(date.today(), jam_masuk) - datetime.combine(date.today(), deadline)).total_seconds()
                            if terlambat_detik > 0:
                                menit, _ = divmod(terlambat_detik, 60)
                                waktu_terlambat = f"{int(menit)} menit"
                        except (TypeError, ValueError): waktu_terlambat = "Error"
                
                if jam_masuk and jam_pulang and status_laporan == 'Hadir':
                    try:
                        total_detik = (datetime.combine(date.today(), jam_pulang) - datetime.combine(date.today(), jam_masuk)).total_seconds()
                        jam, sisa = divmod(total_detik, 3600)
                        menit, _ = divmod(sisa, 60)
                        total_waktu = f"{int(jam)} jam {int(menit)} menit"
                    except (TypeError, ValueError): total_waktu = "Error"

                row = {
                    id_column_name: orang_id, "Nama": orang_obj.nama, "Status": status_laporan,
                    "Jam Masuk": jam_masuk.strftime('%H:%M:%S') if jam_masuk else '-',
                    "Jam Keluar": jam_pulang.strftime('%H:%M:%S') if jam_pulang else '-',
                    "Waktu Terlambat": waktu_terlambat, "Total Waktu": total_waktu
                }
                if tipe_data == 'siswa':
                    row[extra_column_name] = getattr(orang_obj, 'kelas_relasi', None).nama or 'N/A'
                else:
                    row[extra_column_name] = orang_obj.role
                data.append(row)
            
            df = pd.DataFrame(data)
            if not df.empty:
                df = df[[id_column_name, "Nama", extra_column_name, "Status", "Jam Masuk", "Jam Keluar", "Waktu Terlambat", "Total Waktu"]]

        elif jenis_laporan in ["mingguan", "bulanan"]:
            if jenis_laporan == "mingguan":
                if not start_date_str or not end_date_str:
                    flash("Silakan pilih rentang tanggal untuk laporan mingguan.", "danger"); return redirect(url_for("export_bp.export_laporan"))
                start_dt, end_dt = datetime.strptime(start_date_str, "%Y-%m-%d").date(), datetime.strptime(end_date_str, "%Y-%m-%d").date()
                sheet_name = f"Lap {start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b %Y')}"
                filename += f"_mingguan_{start_dt}_{end_dt}"
            else: # Bulanan
                if not bulan or not tahun:
                    flash("Silakan pilih bulan dan tahun untuk laporan bulanan.", "danger"); return redirect(url_for("export_bp.export_laporan"))
                start_dt, end_dt = date(int(tahun), int(bulan), 1), date(int(tahun), int(bulan), calendar.monthrange(int(tahun), int(bulan))[1])
                sheet_name = f"Laporan {calendar.month_name[int(bulan)]} {tahun}"
                filename += f"_bulanan_{bulan}_{tahun}"
            
            status_map = {"Hadir": "H", "Terlambat": "H", "Sakit": "S", "Izin": "I", "Alfa": "A"}
            hasil_absensi = db.session.query(ModelAbsensi).filter(ModelAbsensi.tanggal.between(start_dt, end_dt)).all()
            absensi_dict = {(getattr(absen, id_field_absensi), absen.tanggal): status_map.get(absen.status, "A") for absen in hasil_absensi if absen.jenis_absen in ['masuk', 'lainnya']}

            jadwal_keamanan_dict = {}
            if tipe_data == 'pegawai':
                jadwal_records = JadwalKeamanan.query.filter(JadwalKeamanan.tanggal.between(start_dt, end_dt)).all()
                for jadwal in jadwal_records:
                    if jadwal.pegawai_id not in jadwal_keamanan_dict:
                        jadwal_keamanan_dict[jadwal.pegawai_id] = {}
                    jadwal_keamanan_dict[jadwal.pegawai_id][jadwal.tanggal] = jadwal.shift

            holidays_set = {libur.tanggal for libur in HariLibur.query.filter(HariLibur.tanggal.between(start_dt, end_dt)).all()}
            setting_waktu = SettingWaktu.query.first()
            if setting_waktu and setting_waktu.hari_libur_rutin:
                day_map = {'senin': 0, 'selasa': 1, 'rabu': 2, 'kamis': 3, 'jumat': 4, 'sabtu': 5, 'minggu': 6}
                libur_rutin_idx = {day_map[day.strip()] for day in setting_waktu.hari_libur_rutin.lower().split(',') if day.strip() in day_map}
                for dt in pd.date_range(start_dt, end_dt):
                    if dt.weekday() in libur_rutin_idx: holidays_set.add(dt.date())

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
                    
                    if is_keamanan:
                        pegawai_schedule = jadwal_keamanan_dict.get(orang.id, {})
                        shift_on_day = pegawai_schedule.get(tgl)
                        if shift_on_day == 'Off':
                            status = "-"
                        elif not shift_on_day:
                            status = "A"
                        else:
                            status = absensi_dict.get((getattr(orang, id_field_orang), tgl), "A")
                    else:
                        if tgl in holidays_set:
                            status = "-"
                        else:
                            status = absensi_dict.get((getattr(orang, id_field_orang), tgl), "A")

                    if status == "H": total_hadir += 1
                    elif status == "S": total_sakit += 1
                    elif status == "I": total_izin += 1
                    elif status == "A": total_alfa += 1
                    
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

            # Pemformatan khusus untuk laporan individu
            if jenis_laporan == 'individu':
                bold_format = workbook.add_format({'bold': True, 'align': 'left'})
                # Beri format tebal untuk label total
                worksheet.conditional_format(f'A{len(df)-3}:A{len(df)}', {'type': 'no_blanks', 'format': bold_format})


            for i, col in enumerate(df.columns):
                # Atur format perataan
                column_format = left_format if col in ['Nama', 'Tanggal'] else center_format
                
                # Hitung lebar kolom
                # Untuk kolom 'Tanggal' di laporan individu, beri lebar tetap agar ringkasan terlihat rapi
                if jenis_laporan == 'individu' and col == 'Tanggal':
                    max_len = 20
                else:
                    max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                
                worksheet.set_column(i, i, max_len, column_format)
                
        mimetype, extension = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'
    
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=filename + extension, mimetype=mimetype)