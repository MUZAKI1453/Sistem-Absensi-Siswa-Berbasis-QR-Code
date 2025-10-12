from flask import Blueprint, request, redirect, flash, render_template, url_for
from models import Kelas, Siswa, db
from utils import check_admin_session

# 🟢 Inisialisasi Blueprint dengan prefix URL
kelola_kelas_bp = Blueprint("kelola_kelas_bp", __name__, url_prefix="/kelola_kelas")

# =======================================================================
#  ROUTE: KELOLA DATA KELAS (CRUD)
# =======================================================================
@kelola_kelas_bp.route("/", methods=["GET", "POST"])
def kelola_kelas():
    """Kelola data kelas (tampilkan, tambah, atau update)."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas_edit = None
    edit_id_get = request.args.get("edit_id")
    if edit_id_get:
        kelas_edit = Kelas.query.get(edit_id_get)

    if request.method == "POST":
        edit_id_post = request.form.get("edit_id")
        nama_kelas = request.form["nama_kelas"]

        if edit_id_post:
            kelas_edit_data = Kelas.query.get(edit_id_post)
            if not kelas_edit_data:
                flash("Data kelas tidak ditemukan.", "danger")
                return redirect(url_for("kelola_kelas_bp.kelola_kelas"))

            kelas_lain = Kelas.query.filter(
                Kelas.nama == nama_kelas,
                Kelas.id != kelas_edit_data.id
            ).first()
            if kelas_lain:
                flash(f"Kelas {nama_kelas} sudah ada.", "danger")
                return redirect(url_for("kelola_kelas_bp.kelola_kelas"))

            kelas_edit_data.nama = nama_kelas
            db.session.commit()
            flash("Data kelas berhasil diperbarui", "success")
        else:
            kelas_exist = Kelas.query.filter_by(nama=nama_kelas).first()
            if kelas_exist:
                flash("Kelas ini sudah terdaftar.", "danger")
                return redirect(url_for("kelola_kelas_bp.kelola_kelas"))

            kelas_baru = Kelas(nama=nama_kelas)
            db.session.add(kelas_baru)
            db.session.commit()
            flash("Data kelas berhasil ditambahkan", "success")

        return redirect(url_for("kelola_kelas_bp.kelola_kelas"))

    # GET request
    data_kelas = Kelas.query.order_by(Kelas.nama.asc()).all()
    all_siswa = Siswa.query.all()
    print("=== DEBUG: Daftar Kelas Dimuat ===")
    for k in data_kelas:
        print(f"Kelas ID: {k.id}, Nama: {k.nama}")
    print(f"Total siswa dimuat: {len(all_siswa)}")

    return render_template(
        "kelola_kelas.html",
        kelas=data_kelas,
        all_siswa=all_siswa,
        kelas_edit=kelas_edit
    )


@kelola_kelas_bp.route("/hapus/<int:id>")
def hapus_kelas(id):
    """Hapus data kelas berdasarkan ID."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas = Kelas.query.get(id)
    if kelas:
        siswa_in_kelas = Siswa.query.filter_by(kelas_id=id).first()
        if siswa_in_kelas:
            flash(
                f"Tidak dapat menghapus kelas '{kelas.nama}' karena masih ada siswa di dalamnya.",
                "danger",
            )
        else:
            db.session.delete(kelas)
            db.session.commit()
            flash("Data kelas berhasil dihapus", "success")

    return redirect(url_for("kelola_kelas_bp.kelola_kelas"))
