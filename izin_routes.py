from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db, IzinSiswa
from datetime import datetime
import os

izin_bp = Blueprint("izin_bp", __name__, url_prefix="/izin")

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@izin_bp.route("/", methods=["GET", "POST"])
def form_izin():
    if request.method == "POST":
        nama_ortu = request.form["nama_ortu"]
        no_wa = request.form["no_wa"]
        email = request.form.get("email")
        nama_siswa = request.form["nama_siswa"]
        kelas = request.form["kelas"]
        wali_kelas = request.form["wali_kelas"]
        jenis_izin = request.form["jenis_izin"]
        keterangan = request.form.get("keterangan")

        file_surat = request.files.get("file_surat")
        file_foto = request.files.get("file_foto")

        nama_file_surat = None
        nama_file_foto = None

        if file_surat and file_surat.filename != "":
            nama_file_surat = f"{datetime.now().timestamp()}_{file_surat.filename}"
            file_surat.save(os.path.join(UPLOAD_FOLDER, nama_file_surat))

        if file_foto and file_foto.filename != "":
            nama_file_foto = f"{datetime.now().timestamp()}_{file_foto.filename}"
            file_foto.save(os.path.join(UPLOAD_FOLDER, nama_file_foto))

        izin = IzinSiswa(
            nama_ortu=nama_ortu,
            no_wa=no_wa,
            email=email,
            nama_siswa=nama_siswa,
            kelas=kelas,
            wali_kelas=wali_kelas,
            jenis_izin=jenis_izin,
            keterangan=keterangan,
            file_surat=nama_file_surat,
            file_foto=nama_file_foto,
        )

        db.session.add(izin)
        db.session.commit()

        # Flash pesan sukses (1x)
        flash("✅ Permohonan izin berhasil dikirim. Menunggu persetujuan admin.", "success")
        return redirect(url_for("izin_bp.form_izin"))

    return render_template("izin_form.html")