from flask import Blueprint, render_template, redirect, url_for, flash, request
from models import db, IzinSiswa
from utils import check_admin_session
from datetime import datetime, date

izin_admin_bp = Blueprint("izin_admin_bp", __name__, url_prefix="/admin/izin")


@izin_admin_bp.route("/", methods=["GET"])
def daftar_izin():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Ambil parameter tanggal (jika ada)
    tanggal_str = request.args.get("tanggal")
    query = IzinSiswa.query

    if tanggal_str:
        # Jika admin memilih tanggal tertentu
        try:
            tanggal_filter = datetime.strptime(tanggal_str, "%Y-%m-%d").date()
            query = query.filter(db.func.date(IzinSiswa.tanggal) == tanggal_filter)
        except ValueError:
            flash("Format tanggal tidak valid.", "warning")
    else:
        # Jika tidak memilih (atau baru pertama kali buka halaman)
        # tampilkan hanya data tanggal hari ini
        today = date.today()
        query = query.filter(db.func.date(IzinSiswa.tanggal) == today)
        tanggal_str = today.strftime("%Y-%m-%d")

    # Urutkan dari terbaru ke lama
    data = query.order_by(IzinSiswa.tanggal.desc()).all()

    return render_template("admin_izin_list.html", data=data, tanggal_dipilih=tanggal_str)


@izin_admin_bp.route("/setujui/<int:id>")
def setujui_izin(id):
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    izin = IzinSiswa.query.get_or_404(id)
    izin.status = "Disetujui"
    db.session.commit()
    flash(f"Izin siswa {izin.nama_siswa} telah disetujui.", "success")
    return redirect(url_for("izin_admin_bp.daftar_izin"))


@izin_admin_bp.route("/tolak/<int:id>")
def tolak_izin(id):
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    izin = IzinSiswa.query.get_or_404(id)
    izin.status = "Ditolak"
    db.session.commit()
    flash(f"Izin siswa {izin.nama_siswa} telah ditolak.", "danger")
    return redirect(url_for("izin_admin_bp.daftar_izin"))