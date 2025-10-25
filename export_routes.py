from flask import Blueprint, render_template, request, send_file, redirect, url_for, flash
from datetime import datetime, timedelta
import pandas as pd, io, calendar
from utils import check_admin_session
from models import db, Absensi, Siswa, Pegawai, AbsensiPegawai

export_bp = Blueprint("export_bp", __name__, url_prefix="/export")

@export_bp.route("/", methods=["GET", "POST"])
def export_laporan():
    auth_check = check_admin_session()
    if auth_check: return auth_check
    if request.method == "POST":
        return redirect(url_for("export_bp.download_laporan", **request.form))
    
    tipe_filter = request.args.get('tipe') # Mengambil parameter dari URL
    
    return render_template("export_laporan.html", current_year=datetime.now().year, tipe_filter=tipe_filter)

@export_bp.route("/download_laporan")
def download_laporan():
    auth_check = check_admin_session()
    if auth_check: return auth_check

    tipe_data = request.args.get("tipe_data")
    jenis_laporan = request.args.get("jenis_laporan")
    format_file = request.args.get("format_file")
    tanggal = request.args.get("tanggal")
    bulan = request.args.get("bulan")
    tahun = request.args.get("tahun")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if tipe_data == "siswa":
        ModelAbsensi, ModelOrang = Absensi, Siswa
        join_condition = (Absensi.nis == Siswa.nis)
        id_field_orang, id_field_absensi = "nis", "nis"
    else:
        ModelAbsensi, ModelOrang = AbsensiPegawai, Pegawai
        join_condition = (AbsensiPegawai.no_id == Pegawai.no_id)
        id_field_orang, id_field_absensi = "no_id", "no_id"

    status_map = {"Hadir": "H", "Terlambat": "H", "Sakit": "S", "Izin": "I", "Alfa": "A"}
    semua_orang = ModelOrang.query.order_by(ModelOrang.nama).all()
    
    query_absensi = db.session.query(ModelAbsensi)
    if jenis_laporan == "harian" and tanggal:
        query_absensi = query_absensi.filter(ModelAbsensi.tanggal == tanggal)
    elif jenis_laporan == "bulanan" and bulan and tahun:
        query_absensi = query_absensi.filter(db.extract("month", ModelAbsensi.tanggal) == int(bulan), db.extract("year", ModelAbsensi.tanggal) == int(tahun))
    elif jenis_laporan == "mingguan" and start_date and end_date:
        start_dt, end_dt = datetime.strptime(start_date, "%Y-%m-%d").date(), datetime.strptime(end_date, "%Y-%m-%d").date()
        query_absensi = query_absensi.filter(ModelAbsensi.tanggal.between(start_dt, end_dt))

    hasil_absensi = query_absensi.all()
    absensi_dict = {
        (getattr(absen, id_field_absensi), absen.tanggal): status_map.get(absen.status, "A")
        for absen in hasil_absensi if absen.jenis_absen in ['masuk', 'lainnya']
    }
    
    data = []
    df = pd.DataFrame()

    if jenis_laporan == "harian":
        absensi_harian = db.session.query(ModelAbsensi, ModelOrang).join(ModelOrang, join_condition).filter(ModelAbsensi.tanggal == tanggal).all()
        for absensi, orang in absensi_harian:
            data.append({
                "ID": getattr(orang, id_field_orang), "Nama": orang.nama,
                "Waktu": absensi.waktu.strftime('%H:%M:%S') if absensi.waktu else '-',
                "Status": absensi.status, "Jenis Absen": absensi.jenis_absen
            })
        df = pd.DataFrame(data)
        sheet_name = f"Laporan {tanggal}"
        filename = f"laporan_{tipe_data}_harian_{tanggal}"

    elif jenis_laporan == "bulanan":
        month_name = calendar.month_name[int(bulan)]
        sheet_name = f"Laporan {month_name} {tahun}"
        filename = f"laporan_{tipe_data}_bulanan_{bulan}_{tahun}"
        days_in_month = calendar.monthrange(int(tahun), int(bulan))[1]
        for orang in semua_orang:
            row_data = {"ID": getattr(orang, id_field_orang), "Nama": orang.nama}
            hadir = sum(1 for day in range(1, days_in_month + 1) if absensi_dict.get((getattr(orang, id_field_orang), datetime(int(tahun), int(bulan), day).date()), "A") == "H")
            for day in range(1, days_in_month + 1):
                tgl = datetime(int(tahun), int(bulan), day).date()
                row_data[day] = absensi_dict.get((getattr(orang, id_field_orang), tgl), "A")
            row_data["Total Hadir"] = hadir
            data.append(row_data)
        df = pd.DataFrame(data)

    elif jenis_laporan == "mingguan":
        start_dt, end_dt = datetime.strptime(start_date, "%Y-%m-%d").date(), datetime.strptime(end_date, "%Y-%m-%d").date()
        sheet_name = f"Laporan {start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b %Y')}"
        filename = f"laporan_{tipe_data}_mingguan_{start_dt}_{end_dt}"
        tanggal_range = pd.date_range(start_dt, end_dt)
        kolom_tanggal = [t.day for t in tanggal_range]
        for orang in semua_orang:
            row_data = {"ID": getattr(orang, id_field_orang), "Nama": orang.nama}
            hadir = sum(1 for tgl in tanggal_range if absensi_dict.get((getattr(orang, id_field_orang), tgl.date()), "A") == "H")
            for tgl in tanggal_range:
                row_data[tgl.day] = absensi_dict.get((getattr(orang, id_field_orang), tgl.date()), "A")
            row_data["Total Hadir"] = hadir
            data.append(row_data)
        df = pd.DataFrame(data)
        if not df.empty:
            df = df[["ID", "Nama"] + sorted(kolom_tanggal) + ["Total Hadir"]]

    if df.empty:
        flash("Tidak ada data ditemukan untuk periode tersebut.", "warning")
        return redirect(url_for("export_bp.export_laporan"))

    # ==========================================================
    #  REVISI: LOGIKA UNTUK MEMILIH FORMAT FILE (CSV atau EXCEL)
    # ==========================================================
    output = io.BytesIO()
    if format_file == 'csv':
        df.to_csv(output, index=False)
        mimetype = 'text/csv'
        filename += '.csv'
    else: # Default ke Excel
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        filename += '.xlsx'
    
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=filename, mimetype=mimetype)