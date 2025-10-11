import csv
import io
import os
from flask import Blueprint, request, flash, render_template, redirect, url_for, send_file, current_app
from models import Pegawai, db
from utils import check_admin_session, create_qr_pegawai

pegawai_bp = Blueprint("pegawai_bp", __name__, url_prefix="/pegawai")

# =======================================================================
# ROUTE: KELOLA DATA PEGAWAI
# =======================================================================
@pegawai_bp.route("/", methods=["GET", "POST"])
def pegawai():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    pegawai_edit = None
    edit_id = request.args.get("edit_id")
    if request.method == "POST" and request.form.get("edit_id"):
        edit_id = request.form.get("edit_id")

    if edit_id:
        try:
            pegawai_edit = Pegawai.query.get(int(edit_id))
            if not pegawai_edit:
                flash("ID pegawai tidak valid atau data tidak ditemukan.", "danger")
        except (ValueError, TypeError):
            flash("ID pegawai tidak valid.", "danger")

    if request.method == "POST":
        no_id = request.form.get("no_id")
        nama = request.form.get("nama")
        role = request.form.get("role")

        if not no_id or not nama or not role:
            flash("No ID, nama, dan role harus diisi.", "danger")
            data_pegawai = Pegawai.query.order_by(Pegawai.nama.asc()).all()
            return render_template("pegawai.html", pegawai=data_pegawai, pegawai_edit=pegawai_edit)

        upload_folder = current_app.config['QR_FOLDER_PEGAWAI']
        os.makedirs(upload_folder, exist_ok=True)

        qr_filename = f"{no_id}.png"
        qr_path = os.path.join(upload_folder, qr_filename)
        qr_image = create_qr_pegawai(no_id, nama, role)
        qr_image.save(qr_path)

        if pegawai_edit:
            pegawai_edit.nama = nama
            pegawai_edit.role = role
            pegawai_edit.qr_path = qr_path
            db.session.commit()
            flash("Data pegawai berhasil diperbarui.", "success")
        else:
            if Pegawai.query.filter_by(no_id=no_id).first():
                flash("No ID ini sudah terdaftar.", "danger")
                return redirect(url_for("pegawai_bp.pegawai"))

            pegawai_baru = Pegawai(no_id=no_id, nama=nama, role=role, qr_path=qr_path)
            db.session.add(pegawai_baru)
            db.session.commit()
            flash("Data pegawai berhasil ditambahkan.", "success")

        return redirect(url_for("pegawai_bp.pegawai"))

    # --- FILTER & TAMPIL DATA ---
    cari_nama = request.args.get("cari_nama")
    filter_role = request.args.get("filter_role")

    query = Pegawai.query
    if cari_nama:
        query = query.filter(Pegawai.nama.ilike(f"%{cari_nama}%"))
    if filter_role and filter_role != "":
        query = query.filter(Pegawai.role == filter_role)

    data_pegawai = query.order_by(Pegawai.nama.asc()).all()

    return render_template(
        "pegawai.html",
        pegawai=data_pegawai,
        pegawai_edit=pegawai_edit,
        cari_nama=cari_nama,
        filter_role=filter_role
    )


# =======================================================================
# ROUTE: VIEW & DOWNLOAD QR CODE
# =======================================================================
@pegawai_bp.route('/view_qr/<no_id>')
def view_qr_pegawai(no_id):
    pegawai_data = Pegawai.query.filter_by(no_id=no_id).first()
    if not pegawai_data:
        return "Pegawai tidak ditemukan", 404

    img = create_qr_pegawai(pegawai_data.no_id, pegawai_data.nama, pegawai_data.role)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')


@pegawai_bp.route('/download_qr/<no_id>')
def download_qr_pegawai(no_id):
    pegawai_data = Pegawai.query.filter_by(no_id=no_id).first()
    if not pegawai_data:
        flash("Pegawai tidak ditemukan.", "danger")
        return redirect(url_for("pegawai_bp.pegawai"))

    img = create_qr_pegawai(pegawai_data.no_id, pegawai_data.nama, pegawai_data.role)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    filename = f"{pegawai_data.nama}_{pegawai_data.no_id}.png"
    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=filename)


# =======================================================================
# ROUTE: HAPUS PEGAWAI
# =======================================================================
@pegawai_bp.route("/hapus/<int:id>")
def hapus_pegawai(id):
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    pegawai = Pegawai.query.get(id)
    if pegawai:
        if pegawai.qr_path and os.path.exists(pegawai.qr_path):
            try:
                os.remove(pegawai.qr_path)
            except Exception as e:
                print(f"Gagal menghapus QR {pegawai.qr_path}: {e}")

        db.session.delete(pegawai)
        db.session.commit()
        flash("Data pegawai berhasil dihapus.", "success")

    return redirect(url_for("pegawai_bp.pegawai"))


# =======================================================================
# ROUTE: IMPORT PEGAWAI
# =======================================================================
@pegawai_bp.route("/import", methods=["POST"])
def import_pegawai():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    if 'csv_file' not in request.files:
        flash("Tidak ada file yang dipilih.", "danger")
        return redirect(url_for("pegawai_bp.pegawai"))

    file = request.files['csv_file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash("Pilih file CSV yang valid.", "danger")
        return redirect(url_for("pegawai_bp.pegawai"))

    try:
        stream = io.StringIO(file.stream.read().decode("UTF-8"))
        csv_input = csv.DictReader(stream)

        upload_folder = current_app.config['QR_FOLDER_PEGAWAI']
        os.makedirs(upload_folder, exist_ok=True)

        count_new = 0
        count_skip = 0

        for row in csv_input:
            no_id = row.get("no_id")
            nama = row.get("nama")
            role = row.get("role")

            if not no_id or not nama or not role:
                count_skip += 1
                continue

            if Pegawai.query.filter_by(no_id=no_id).first():
                count_skip += 1
                continue

            qr_filename = f"{no_id}.png"
            qr_path = os.path.join(upload_folder, qr_filename)
            qr_image = create_qr_pegawai(no_id, nama, role)
            qr_image.save(qr_path)

            pegawai_baru = Pegawai(no_id=no_id, nama=nama, role=role, qr_path=qr_path)
            db.session.add(pegawai_baru)
            count_new += 1

        db.session.commit()
        flash(f"Impor selesai: {count_new} pegawai baru ditambahkan, {count_skip} dilewati.", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Terjadi kesalahan saat mengimpor: {str(e)}", "danger")

    return redirect(url_for("pegawai_bp.pegawai"))