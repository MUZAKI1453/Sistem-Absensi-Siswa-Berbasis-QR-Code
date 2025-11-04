import csv
import io
import os
import zipfile
from datetime import datetime

from flask import Blueprint, flash, request, render_template, url_for, redirect, send_file, current_app

from models import Siswa, Kelas, db
from utils import create_qr_siswa, check_admin_session

# 🟢 Inisialisasi Blueprint
siswa_bp = Blueprint("siswa_bp", __name__, url_prefix="/siswa")


# =======================================================================
# ROUTE: KELOLA DATA SISWA (CRUD & Filter)
# =======================================================================
@siswa_bp.route("/", methods=["GET", "POST"])
def siswa():
    """Kelola data siswa (tambah, edit, dan tampilkan daftar)."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    siswa_edit = None
    edit_id = request.args.get("edit_id")

    if request.method == "POST":
        edit_id = request.form.get("edit_id")

    if edit_id:
        try:
            siswa_edit = Siswa.query.get(int(edit_id))
            if not siswa_edit:
                flash("ID siswa tidak valid atau data tidak ditemukan.", "danger")
                siswa_edit = None
        except (ValueError, TypeError):
            flash("ID siswa tidak valid.", "danger")
            siswa_edit = None

    if request.method == "POST":
        nis = request.form.get("nis")
        nama = request.form.get("nama")
        kelas_id = request.form.get("kelas")
        no_hp = request.form.get("no_hp")

        if not nis or not nama or not kelas_id:
            flash("NIS, nama, dan kelas harus diisi.", "danger")
            semua_kelas = Kelas.query.order_by(Kelas.nama.asc()).all()
            data_siswa = Siswa.query.order_by(Siswa.nama.asc()).all()
            return render_template(
                "siswa.html",
                siswa=data_siswa,
                siswa_edit=siswa_edit,
                semua_kelas=semua_kelas
            )

        # 🟢 Gunakan folder khusus siswa
        upload_folder = current_app.config['QR_FOLDER_SISWA']
        os.makedirs(upload_folder, exist_ok=True)

        qr_filename = f"{nis}.png"
        qr_path = os.path.join(upload_folder, qr_filename)
        qr_image = create_qr_siswa(nis, nama)
        qr_image.save(qr_path)

        if siswa_edit:
            siswa_edit.nama = nama
            siswa_edit.kelas_id = int(kelas_id)
            siswa_edit.no_hp_ortu = no_hp
            siswa_edit.qr_path = qr_path
            db.session.commit()
            flash("Data siswa berhasil diperbarui", "success")
        else:
            siswa_exist = Siswa.query.filter_by(nis=nis).first()
            if siswa_exist:
                flash("NIS ini sudah terdaftar.", "danger")
                return redirect(url_for("siswa_bp.siswa"))

            siswa_baru = Siswa(
                nis=nis,
                nama=nama,
                kelas_id=int(kelas_id),
                no_hp_ortu=no_hp,
                qr_path=qr_path
            )
            db.session.add(siswa_baru)
            db.session.commit()
            flash("Data siswa berhasil ditambahkan", "success")

        return redirect(url_for("siswa_bp.siswa"))

    # --- FILTER & TAMPIL DATA ---
    cari_nama = request.args.get("cari_nama")
    filter_kelas_id = request.args.get("filter_kelas")

    query = Siswa.query
    if cari_nama:
        query = query.filter(Siswa.nama.ilike(f"%{cari_nama}%"))
    if filter_kelas_id and filter_kelas_id != "":
        query = query.filter(Siswa.kelas_id == filter_kelas_id)

    data_siswa = query.order_by(Siswa.nama.asc()).all()
    semua_kelas = Kelas.query.order_by(Kelas.nama.asc()).all()

    return render_template(
        "siswa.html",
        siswa=data_siswa,
        siswa_edit=siswa_edit,
        cari_nama=cari_nama,
        filter_kelas_id=filter_kelas_id,
        semua_kelas=semua_kelas
    )


# =======================================================================
# ROUTE: HAPUS SISWA
# =======================================================================
@siswa_bp.route("/hapus_siswa/<int:id>")
def hapus_siswa(id):
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    siswa_to_delete = Siswa.query.get(id)
    if siswa_to_delete:
        if siswa_to_delete.qr_path and os.path.exists(siswa_to_delete.qr_path):
            try:
                os.remove(siswa_to_delete.qr_path)
            except Exception as e:
                print(f"Gagal menghapus file QR {siswa_to_delete.qr_path}: {e}")

        db.session.delete(siswa_to_delete)
        db.session.commit()
        flash("Data siswa berhasil dihapus", "success")
    else:
        flash("Siswa tidak ditemukan.", "danger")

    return redirect(url_for("siswa_bp.siswa"))


# =======================================================================
# ROUTE: DOWNLOAD & VIEW QR CODE
# =======================================================================
@siswa_bp.route('/download_qr/<nis>')
def download_qr(nis):
    siswa_data = Siswa.query.filter_by(nis=nis).first()
    if not siswa_data:
        flash("Siswa tidak ditemukan.", "danger")
        return redirect(url_for("siswa_bp.siswa"))

    img = create_qr_siswa(siswa_data.nis, siswa_data.nama)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    filename = f"{siswa_data.nama}_{siswa_data.nis}.png"
    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=filename)


@siswa_bp.route('/view_qr/<nis>')
def view_qr(nis):
    siswa_data = Siswa.query.filter_by(nis=nis).first()
    if not siswa_data:
        return "Siswa tidak ditemukan", 404

    img = create_qr_siswa(siswa_data.nis, siswa_data.nama)
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')


# =======================================================================
# ROUTE: IMPORT DATA SISWA
# =======================================================================
# =======================================================================
# ROUTE: DOWNLOAD SEMUA QR CODE SISWA (DENGAN SUBFOLDER PER KELAS)
# =======================================================================
@siswa_bp.route("/download_all_qr")
def download_all_qr():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Folder dasar untuk simpan sementara ZIP
    base_folder = current_app.config["QR_FOLDER_SISWA"]
    os.makedirs(base_folder, exist_ok=True)

    # Buat folder sementara untuk isi ZIP
    temp_folder = os.path.join(base_folder, "all_qr_temp")
    os.makedirs(temp_folder, exist_ok=True)

    # Ambil semua data siswa + kelas
    siswa_data = Siswa.query.join(Kelas).order_by(Kelas.nama.asc(), Siswa.nama.asc()).all()

    for siswa in siswa_data:
        kelas_folder = os.path.join(temp_folder, siswa.kelas_relasi.nama)
        os.makedirs(kelas_folder, exist_ok=True)

        # Generate QR (pastikan selalu terbaru)
        qr_filename = f"{siswa.nis}_{siswa.nama}.png"
        qr_path = os.path.join(kelas_folder, qr_filename)

        qr_image = create_qr_siswa(siswa.nis, siswa.nama)
        qr_image.save(qr_path)

    # Nama file ZIP hasil
    zip_filename = f"qr_siswa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(base_folder, zip_filename)

    # Buat file ZIP
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(temp_folder):
            for file in files:
                file_path = os.path.join(root, file)
                # Struktur di dalam ZIP tetap ada folder per kelas
                arcname = os.path.relpath(file_path, temp_folder)
                zipf.write(file_path, arcname)

    # Bersihkan folder sementara
    import shutil
    shutil.rmtree(temp_folder, ignore_errors=True)

    return send_file(zip_path, mimetype="application/zip", as_attachment=True, download_name=zip_filename)


# =======================================================================
# ROUTE: IMPORT DATA SISWA
# =======================================================================
@siswa_bp.route("/import_siswa", methods=["POST"])
def import_siswa():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    if "csv_file" not in request.files:
        flash("File CSV tidak ditemukan.", "danger")
        return redirect(url_for("siswa_bp.siswa"))

    file = request.files["csv_file"]
    if file.filename == "":
        flash("Nama file tidak valid.", "danger")
        return redirect(url_for("siswa_bp.siswa"))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        csv_input = csv.DictReader(stream)

        upload_folder = current_app.config['QR_FOLDER_SISWA']
        os.makedirs(upload_folder, exist_ok=True)

        count_new = 0
        count_update = 0
        for row in csv_input:
            nis = row.get("nis")
            nama = row.get("nama")
            no_hp = row.get("no_hp")
            kelas_nama = row.get("kelas")

            if not nis or not nama or not kelas_nama:
                continue

            kelas = Kelas.query.filter_by(nama=kelas_nama).first()
            if not kelas:
                flash(f"Kelas '{kelas_nama}' tidak ditemukan, data {nama} dilewati.", "warning")
                continue

            qr_filename = f"{nis}.png"
            qr_path = os.path.join(upload_folder, qr_filename)
            qr_image = create_qr_siswa(nis, nama)
            qr_image.save(qr_path)

            siswa_exist = Siswa.query.filter_by(nis=nis).first()
            if siswa_exist:
                siswa_exist.nama = nama
                siswa_exist.kelas_id = kelas.id
                siswa_exist.no_hp_ortu = no_hp
                siswa_exist.qr_path = qr_path
                count_update += 1
            else:
                siswa_baru = Siswa(
                    nis=nis,
                    nama=nama,
                    kelas_id=kelas.id,
                    no_hp_ortu=no_hp,
                    qr_path=qr_path
                )
                db.session.add(siswa_baru)
                count_new += 1

        db.session.commit()
        flash(f"Impor selesai: {count_new} siswa baru, {count_update} diperbarui.", "success")

    except Exception as e:
        flash(f"Terjadi kesalahan saat mengimpor: {str(e)}", "danger")

    return redirect(url_for("siswa_bp.siswa"))
