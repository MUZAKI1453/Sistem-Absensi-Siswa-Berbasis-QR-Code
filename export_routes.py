from flask import Blueprint, render_template, request, send_file, redirect, url_for, flash
from datetime import datetime, timedelta
import pandas as pd, io, calendar
from utils import check_admin_session
from models import db, Absensi, Siswa, Pegawai, AbsensiPegawai

# Inisialisasi Blueprint dengan prefix URL
export_bp = Blueprint("export_bp", __name__, url_prefix="/export")

# ======================================================================
#  HALAMAN UTAMA EXPORT
# ======================================================================
@export_bp.route("/", methods=["GET", "POST"])
def export_laporan():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    if request.method == "POST":
        tipe_data = request.form.get("tipe_data")
        jenis_laporan = request.form.get("jenis_laporan")
        format_file = request.form.get("format_file")
        tanggal = request.form.get("tanggal")
        bulan = request.form.get("bulan")
        tahun = request.form.get("tahun")
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date")

        # Redirect ke fungsi ekspor sesuai pilihan
        return redirect(url_for("export_bp.download_laporan",
                                tipe_data=tipe_data,
                                jenis_laporan=jenis_laporan,
                                format_file=format_file,
                                tanggal=tanggal,
                                bulan=bulan,
                                tahun=tahun,
                                start_date=start_date,
                                end_date=end_date))

    return render_template("export_laporan.html", current_year=datetime.now().year)


# ======================================================================
#  FUNGSI EKSPOR DATA (HARlAN / BULANAN / MINGGUAN)
# ======================================================================
@export_bp.route("/download_laporan")
def download_laporan():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    tipe_data = request.args.get("tipe_data")
    jenis_laporan = request.args.get("jenis_laporan")
    format_file = request.args.get("format_file")
    tanggal = request.args.get("tanggal")
    bulan = request.args.get("bulan")
    tahun = request.args.get("tahun")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # Tentukan model dan relasi
    if tipe_data == "siswa":
        query = db.session.query(Absensi, Siswa).join(Siswa, Absensi.nis == Siswa.nis)
        ModelAbsensi = Absensi
    else:
        query = db.session.query(AbsensiPegawai, Pegawai).join(Pegawai, AbsensiPegawai.no_id == Pegawai.no_id)
        ModelAbsensi = AbsensiPegawai

    # Filter laporan
    if jenis_laporan == "harian" and tanggal:
        query = query.filter(ModelAbsensi.tanggal == tanggal)
    elif jenis_laporan == "bulanan" and bulan and tahun:
        query = query.filter(db.extract("month", ModelAbsensi.tanggal) == int(bulan))
        query = query.filter(db.extract("year", ModelAbsensi.tanggal) == int(tahun))
    elif jenis_laporan == "mingguan" and start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        query = query.filter(ModelAbsensi.tanggal.between(start_dt, end_dt))

    hasil = query.all()

    if not hasil:
        flash("Tidak ada data ditemukan untuk periode tersebut.", "warning")
        return redirect(url_for("export_bp.export_laporan"))

    # Susun data
    data = []
    for absensi, orang in hasil:
        if absensi.status == "Terlambat":
            status_laporan = "Hadir (Terlambat)"
        else:
            status_laporan = absensi.status

        data.append({
            "Nama": orang.nama,
            "ID": getattr(orang, "nis", getattr(orang, "no_id", None)),
            "Tanggal": absensi.tanggal.strftime("%Y-%m-%d"),
            "Hari": absensi.tanggal.strftime("%A"),
            "Waktu": absensi.waktu.strftime('%H:%M:%S'),
            "Status": status_laporan
        })

    df = pd.DataFrame(data)

    # ==========================================================
    #  LAPORAN HARIAN
    # ==========================================================
    if jenis_laporan == "harian":
        sheet_name = f"Laporan {tanggal}"
        filename = f"laporan_{tipe_data}_harian_{tanggal}"

    # ==========================================================
    #  LAPORAN BULANAN (format tabel per hari)
    # ==========================================================
    elif jenis_laporan == "bulanan":
        month_name = calendar.month_name[int(bulan)]
        sheet_name = f"Laporan {month_name} {tahun}"
        filename = f"laporan_{tipe_data}_bulanan_{bulan}_{tahun}"

        df["Hari"] = pd.to_datetime(df["Tanggal"]).dt.day
        df_pivot = df.pivot_table(index=["Nama", "ID"], columns="Hari", values="Status", aggfunc=lambda x: ", ".join(x))
        df_pivot = df_pivot.reset_index()

        # pastikan kolom sesuai jumlah hari di bulan tsb
        days_in_month = calendar.monthrange(int(tahun), int(bulan))[1]
        for d in range(1, days_in_month + 1):
            if d not in df_pivot.columns:
                df_pivot[d] = "-"

        df_pivot = df_pivot[["Nama", "ID"] + list(range(1, days_in_month + 1))]
        df_pivot["Total Hadir"] = df_pivot.apply(lambda r: sum("Hadir" in str(v) for v in r.values), axis=1)
        df = df_pivot

    # ==========================================================
    #  LAPORAN MINGGUAN (format mirip bulanan, tapi range)
    # ==========================================================
    elif jenis_laporan == "mingguan":
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        sheet_name = f"Laporan {start_dt.strftime('%d %b')} - {end_dt.strftime('%d %b %Y')}"
        filename = f"laporan_{tipe_data}_mingguan_{start_dt}_{end_dt}"

        df["Hari"] = pd.to_datetime(df["Tanggal"]).dt.day
        df_pivot = df.pivot_table(index=["Nama", "ID"], columns="Tanggal", values="Status", aggfunc=lambda x: ", ".join(x))
        df_pivot = df_pivot.reset_index()

        tanggal_range = pd.date_range(start_dt, end_dt)
        for t in tanggal_range:
            col = t.strftime("%Y-%m-%d")
            if col not in df_pivot.columns:
                df_pivot[col] = "-"

        df_pivot = df_pivot[["Nama", "ID"] + [t.strftime("%Y-%m-%d") for t in tanggal_range]]
        df_pivot["Total Hadir"] = df_pivot.apply(lambda r: sum("Hadir" in str(v) for v in r.values), axis=1)
        df = df_pivot

    # ==========================================================
    #  EXPORT FILE
    # ==========================================================
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"{filename}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
