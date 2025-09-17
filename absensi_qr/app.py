import os
import io
from datetime import datetime, time

# Third-party libraries
import pandas as pd
import qrcode
import requests
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, jsonify, send_from_directory, flash
)
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import and_

# Local imports
from models import db, Siswa, Absensi, SettingWaktu, Kelas

# =======================================================================
#  INISIALISASI APLIKASI FLASK
# =======================================================================
app = Flask(__name__)
app.secret_key = "absensi_qr_secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///absensi.db'
app.config['UPLOAD_FOLDER'] = 'static/qr_codes'
db.init_app(app)

# Membuat database dan folder jika belum ada
with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# =======================================================================
#  FUNGSI HELPER & UTILITAS
# =======================================================================
def format_nomor_hp(nomor):
    """
    Memformat nomor HP ke format internasional (62...).
    Misalnya: '0812...' -> '62812...'
    """
    nomor = nomor.strip()
    if nomor.startswith("0"):
        return "62" + nomor[1:]
    elif nomor.startswith("+62"):
        return nomor[1:]
    return nomor


def check_admin_session():
    """
    Fungsi helper untuk memeriksa apakah admin sudah login.
    Jika belum, akan mengarahkan ke halaman login.
    """
    if "admin" not in session:
        return redirect(url_for("login"))
    return None


def create_qr_with_text(nis, nama):
    """
    Membuat QR code dan menambahkan teks (nama & NIS) di bawahnya.
    """
    # Membuat QR code dasar
    qr_img = qrcode.make(nis)
    qr_img_pil = qr_img.convert("RGB")
    qr_width, qr_height = qr_img_pil.size

    # Ukuran gambar akhir
    final_width = max(qr_width, 300)
    final_height = qr_height + 80  # Tambahan ruang untuk dua baris teks

    final_image = Image.new("RGB", (final_width, final_height), "white")

    # Menempatkan QR code di bagian atas gambar baru
    qr_x_pos = (final_width - qr_width) // 2
    final_image.paste(qr_img_pil, (qr_x_pos, 0))

    draw = ImageDraw.Draw(final_image)

    try:
        # Mencoba memuat font yang ada di sistem
        font_nama = ImageFont.truetype("arial.ttf", 24)
        font_nis = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        # Jika 'arial.ttf' tidak ditemukan, gunakan font default
        font_nama = ImageFont.load_default()
        font_nis = ImageFont.load_default()

    # Menyiapkan teks untuk nama dan NIS
    text_nama = nama
    text_nis = nis

    # Menggunakan draw.textbbox() untuk mendapatkan ukuran teks nama
    bbox_nama = draw.textbbox((0, 0), text_nama, font=font_nama)
    text_width_nama = bbox_nama[2] - bbox_nama[0]

    # Menggunakan draw.textbbox() untuk mendapatkan ukuran teks NIS
    bbox_nis = draw.textbbox((0, 0), text_nis, font=font_nis)
    text_width_nis = bbox_nis[2] - bbox_nis[0]

    # Menghitung posisi X agar teks berada di tengah
    text_x_pos_nama = (final_width - text_width_nama) // 2
    text_x_pos_nis = (final_width - text_width_nis) // 2

    # Menentukan posisi Y untuk setiap baris teks
    text_y_pos_nama = qr_height + 5  # Di bawah QR code
    text_y_pos_nis = text_y_pos_nama + 25  # Di bawah nama

    # Menggambar teks pada gambar
    draw.text((text_x_pos_nama, text_y_pos_nama), text_nama, font=font_nama, fill="black")
    draw.text((text_x_pos_nis, text_y_pos_nis), text_nis, font=font_nis, fill="black")

    return final_image

def get_badge_color(status):
    """
    Fungsi filter Jinja2 untuk menentukan warna badge berdasarkan status.
    """
    if status == 'Hadir' or status == 'Terlambat':
        return 'success'
    elif status == 'Izin':
        return 'warning text-dark'
    elif status == 'Sakit':
        return 'info text-dark'
    else:
        return 'danger'

# Mendaftarkan fungsi sebagai filter di Jinja2
app.jinja_env.filters['get_badge_color'] = get_badge_color

# =======================================================================
#  ROUTE: AUTENTIKASI ADMIN
# =======================================================================
@app.route("/", methods=["GET", "POST"])
def login():
    """Rute untuk halaman login admin."""
    if request.method == "POST":
        # Peringatan: Gunakan metode autentikasi yang lebih aman di lingkungan produksi
        if request.form["username"] == "admin" and request.form["password"] == "123":
            session["admin"] = True
            return redirect(url_for("dashboard"))
        else:
            flash("Username atau password salah.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Rute untuk logout, menghapus session admin."""
    session.clear()
    flash("Anda telah berhasil logout.", "success")
    return redirect(url_for("login"))


# =======================================================================
#  ROUTE: DASHBOARD UTAMA
# =======================================================================
@app.route("/dashboard")
def dashboard():
    """Menampilkan dashboard dengan statistik absensi hari ini."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    hari_ini = datetime.today().date()

    total_siswa = Siswa.query.count()
    total_kelas = Kelas.query.count()

    total_hadir = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status.in_(["Hadir", "Terlambat"]),
        Absensi.jenis_absen == "masuk"
    ).distinct(Absensi.nis).count()

    total_terlambat = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Terlambat",
        Absensi.jenis_absen == "masuk"
    ).distinct(Absensi.nis).count()

    total_sakit = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Sakit"
    ).distinct(Absensi.nis).count()

    total_izin = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Izin"
    ).distinct(Absensi.nis).count()

    total_alfa = total_siswa - (total_hadir + total_sakit + total_izin)

    return render_template(
        "dashboard.html",
        total_hadir=total_hadir,
        total_terlambat=total_terlambat,
        total_sakit=total_sakit,
        total_izin=total_izin,
        total_alfa=total_alfa,
        total_siswa=total_siswa,
        total_kelas=total_kelas
    )

# =======================================================================
#  ROUTE: KELOLA DATA SISWA (CRUD)
# =======================================================================
@app.route("/siswa", methods=["GET", "POST"])
def siswa():
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    siswa_edit = None
    edit_id = request.args.get("edit_id")
    if request.method == "POST":
        form_edit_id = request.form.get("edit_id")
        if form_edit_id:
            edit_id = form_edit_id

    if edit_id:
        try:
            siswa_edit = Siswa.query.get(int(edit_id))
            if not siswa_edit:
                flash("ID siswa tidak valid atau data tidak ditemukan.", "danger")
        except (ValueError, TypeError):
            flash("ID siswa tidak valid.", "danger")

    if request.method == "POST":
        nis = request.form.get("nis")
        nama = request.form.get("nama")
        kelas_id = request.form.get("kelas")
        no_hp = request.form.get("no_hp")

        # Validasi dasar
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

        if siswa_edit:
            # Mode EDIT
            siswa_edit.nama = nama
            siswa_edit.kelas_id = int(kelas_id)
            siswa_edit.no_hp_ortu = no_hp

            # Update QR Code (pakai nis yang sama, karena readonly)
            qr_filename = f"{siswa_edit.nis}.png"
            qr_path = os.path.join(app.config['UPLOAD_FOLDER'], qr_filename)
            qr_image = create_qr_with_text(siswa_edit.nis, nama)
            qr_image.save(qr_path)
            siswa_edit.qr_path = qr_path

            db.session.commit()
            flash("Data siswa berhasil diperbarui", "success")
        else:
            # Mode TAMBAH
            siswa_exist = Siswa.query.filter_by(nis=nis).first()
            if siswa_exist:
                flash("NIS ini sudah terdaftar.", "danger")
                return redirect(url_for("siswa"))

            qr_filename = f"{nis}.png"
            qr_path = os.path.join(app.config['UPLOAD_FOLDER'], qr_filename)
            qr_image = create_qr_with_text(nis, nama)
            qr_image.save(qr_path)

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

        return redirect(url_for("siswa"))

    else:  # Logika untuk Menampilkan Halaman (GET)
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


@app.route("/hapus_siswa/<int:id>")
def hapus_siswa(id):
    """Menghapus data siswa berdasarkan ID."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    siswa = Siswa.query.get(id)
    if siswa:
        if siswa.qr_path and os.path.exists(siswa.qr_path):
            os.remove(siswa.qr_path)
        db.session.delete(siswa)
        db.session.commit()
        flash("Data siswa berhasil dihapus", "success")
    return redirect(url_for("siswa"))


@app.route('/download_qr/<nis>')
def download_qr(nis):
    """
    Mengunduh file QR Code siswa dengan teks.
    """
    siswa_data = Siswa.query.filter_by(nis=nis).first()
    if not siswa_data:
        flash("Siswa tidak ditemukan.", "danger")
        return redirect(url_for("siswa"))

    qr_image = create_qr_with_text(siswa_data.nis, siswa_data.nama)

    img_io = io.BytesIO()
    qr_image.save(img_io, 'PNG')
    img_io.seek(0)

    filename = f"{siswa_data.nama}_{siswa_data.nis}.png"

    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name=filename)


@app.route('/view_qr/<nis>')
def view_qr(nis):
    """
    Rute untuk menampilkan gambar QR Code dengan teks di browser.
    """
    siswa_data = Siswa.query.filter_by(nis=nis).first()
    if not siswa_data:
        return "Siswa tidak ditemukan", 404

    img = create_qr_with_text(siswa_data.nis, siswa_data.nama)

    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')


# =======================================================================
#  ROUTE: KELOLA DATA KELAS (CRUD)
# =======================================================================
@app.route("/kelola_kelas", methods=["GET", "POST"])
def kelola_kelas():
    """
    Mengelola data kelas.
    - GET: Menampilkan daftar kelas.
    - POST: Menambah atau mengupdate data kelas.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas_edit = None
    edit_id_get = request.args.get("edit_id")
    if edit_id_get:
        kelas_edit = Kelas.query.get(edit_id_get)

    if request.method == "POST":
        # TAMBAH BARIS INI
        edit_id_post = request.form.get("edit_id")

        nama_kelas = request.form["nama_kelas"]

        # Periksa apakah ini mode edit atau tambah
        if edit_id_post:  # Menggunakan ID dari form
            kelas_edit_data = Kelas.query.get(edit_id_post)

            # Logika validasi dan update
            if not kelas_edit_data:
                flash("Data kelas tidak ditemukan.", "danger")
                return redirect(url_for("kelola_kelas"))

            kelas_lain = Kelas.query.filter(Kelas.nama == nama_kelas, Kelas.id != kelas_edit_data.id).first()
            if kelas_lain:
                flash(f"Kelas {nama_kelas} sudah ada.", "danger")
                return redirect(url_for("kelola_kelas"))

            kelas_edit_data.nama = nama_kelas
            db.session.commit()
            flash("Data kelas berhasil diperbarui", "success")
        else:  # Mode Tambah
            kelas_exist = Kelas.query.filter_by(nama=nama_kelas).first()
            if kelas_exist:
                flash("Kelas ini sudah terdaftar.", "danger")
                return redirect(url_for("kelola_kelas"))

            kelas_baru = Kelas(nama=nama_kelas)
            db.session.add(kelas_baru)
            db.session.commit()
            flash("Data kelas berhasil ditambahkan", "success")

        return redirect(url_for("kelola_kelas"))

    else:
        data_kelas = Kelas.query.order_by(Kelas.nama.asc()).all()
        return render_template("kelola_kelas.html", kelas=data_kelas, kelas_edit=kelas_edit)

@app.route("/hapus_kelas/<int:id>")
def hapus_kelas(id):
    """Menghapus data kelas berdasarkan ID."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas = Kelas.query.get(id)
    if kelas:
        # Periksa apakah ada siswa di kelas ini
        siswa_in_kelas = Siswa.query.filter_by(kelas_id=id).first()
        if siswa_in_kelas:
            flash(f"Tidak dapat menghapus kelas '{kelas.nama}' karena masih ada siswa di dalamnya.", "danger")
        else:
            db.session.delete(kelas)
            db.session.commit()
            flash("Data kelas berhasil dihapus", "success")
    return redirect(url_for("kelola_kelas"))


# =======================================================================
#  ROUTE: PROSES ABSENSI & SCANNER
# =======================================================================
@app.route("/scan")
def scan():
    """Menampilkan halaman scanner QR."""
    return render_template("scan.html")


@app.route("/submit_scan", methods=["POST"])
def submit_scan():
    """
    Memproses hasil scan QR Code untuk mencatat absensi.
    Respons diubah menjadi JSON agar notifikasi spontan.
    """
    nis = request.form.get("nis")
    siswa = Siswa.query.filter_by(nis=nis).first()

    if not siswa:
        # Mengirim respons JSON jika QR tidak terdaftar
        return jsonify({
            'status': 'danger',
            'message': 'QR tidak terdaftar'
        })

    now = datetime.now()
    hari_ini = now.date()
    waktu_skrg = now.time()

    setting = SettingWaktu.query.first()
    if not setting:
        return jsonify({
            'status': 'danger',
            'message': 'Pengaturan waktu absensi belum dibuat oleh admin'
        })

    jenis_absen = None
    status_absen_db = None  # Status yang akan disimpan di database
    pesan_status_wa = None  # Status yang akan dikirim ke WhatsApp

    # Periksa waktu absensi masuk
    if setting.jam_masuk_mulai <= waktu_skrg <= setting.jam_masuk_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Hadir"
        pesan_status_wa = "Hadir"
    # Periksa waktu terlambat
    elif setting.jam_terlambat_selesai and setting.jam_masuk_selesai < waktu_skrg <= setting.jam_terlambat_selesai:
        jenis_absen = "masuk"
        status_absen_db = "Terlambat"  # Status ini tetap 'Terlambat' di database
        pesan_status_wa = "Terlambat"  # Status 'Terlambat' akan muncul di notifikasi WA
    # Periksa waktu absensi pulang
    elif setting.jam_pulang_mulai <= waktu_skrg <= setting.jam_pulang_selesai:
        jenis_absen = "pulang"
        status_absen_db = "Hadir"
        pesan_status_wa = "Hadir"
    else:
        return jsonify({
            'status': 'danger',
            'message': 'Bukan waktu absensi'
        })

    sudah_absen = Absensi.query.filter_by(
        nis=nis,
        tanggal=hari_ini,
        jenis_absen=jenis_absen
    ).first()
    if sudah_absen:
        return jsonify({
            'status': 'warning',
            'message': f"Sudah absen {jenis_absen} hari ini"
        })

    absensi = Absensi(
        nis=nis,
        status=status_absen_db,  # Gunakan status database
        jenis_absen=jenis_absen,
        tanggal=hari_ini,
        waktu=now.time()
    )
    db.session.add(absensi)
    db.session.commit()

    nomor = format_nomor_hp(siswa.no_hp_ortu)
    # Gunakan status yang berbeda untuk pesan WA
    pesan = f"Siswa {siswa.nama} ({siswa.nis}) telah absen {jenis_absen} dengan status {pesan_status_wa} pada {now.strftime('%H:%M')}"

    # ... (lanjutan kode kirim WA) ...
    try:
        FONNTE_TOKEN = "m7sWNBLHrGi2AHZNj2x3"
        url = "https://api.fonnte.com/send"
        headers = {"Authorization": FONNTE_TOKEN}
        data = {"target": nomor, "message": pesan}
        response = requests.post(url, headers=headers, data=data)

        if response.status_code == 200:
            return jsonify({
                'status': 'success',
                'message': f"Absen {jenis_absen} berhasil ({status_absen_db}) & WA terkirim"
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': f"Absen {jenis_absen} berhasil ({status_absen_db}), tapi notifikasi WA gagal. Kode: {response.status_code}"
            })
    except Exception as e:
        return jsonify({
            'status': 'warning',
            'message': f"Absen {jenis_absen} berhasil ({status_absen_db}), tapi notifikasi WA gagal: {str(e)}"
        })


# =======================================================================
#  ROUTE: KELOLA DATA ABSENSI
# =======================================================================
@app.route("/absensi", methods=["GET"])
def absensi():
    """
    Menampilkan data absensi harian dan memungkinkan filter per kelas dan pencarian nama.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    hari_ini = datetime.today().date()
    kelas_id = request.args.get("kelas_id")
    cari_nama = request.args.get("cari_nama")
    kelas_list = Kelas.query.order_by(Kelas.nama.asc()).all()

    # Query utama untuk mendapatkan SEMUA siswa berdasarkan filter
    # Menggunakan join agar bisa mengakses data kelas
    siswa_query = Siswa.query.join(Kelas)

    # Jika ada pencarian nama, tambahkan filter nama
    if cari_nama:
        siswa_query = siswa_query.filter(Siswa.nama.ilike(f"%{cari_nama}%"))

    # Jika ada filter kelas, tambahkan filter kelas
    if kelas_id:
        siswa_query = siswa_query.filter(Siswa.kelas_id == kelas_id)

    # Ambil semua siswa yang telah difilter
    semua_siswa = siswa_query.order_by(Siswa.nama.asc()).all()

    # Ambil semua data absensi hari ini dalam satu query efisien
    absensi_hari_ini = Absensi.query.filter(Absensi.tanggal == hari_ini).all()
    absensi_dict = {}
    for absen in absensi_hari_ini:
        if absen.nis not in absensi_dict:
            absensi_dict[absen.nis] = {'masuk': None, 'pulang': None}
        if absen.jenis_absen == 'masuk':
            absensi_dict[absen.nis]['masuk'] = absen
        elif absen.jenis_absen == 'pulang':
            absensi_dict[absen.nis]['pulang'] = absen
        elif absen.jenis_absen == 'lainnya':
            absensi_dict[absen.nis]['masuk'] = absen
            absensi_dict[absen.nis]['pulang'] = absen

    # Buat dictionary final dengan data siswa dan absensi
    data_absensi = {}
    for siswa in semua_siswa:
        data_absensi[siswa.nis] = {
            "siswa": siswa,
            "masuk": absensi_dict.get(siswa.nis, {}).get('masuk'),
            "pulang": absensi_dict.get(siswa.nis, {}).get('pulang')
        }

    # Urutkan data absensi untuk memastikan yang sudah absen tampil di atas
    # Anda bisa menyortir data_absensi sebelum mengirimkannya ke template jika diperlukan
    data_absensi_terurut = sorted(
        data_absensi.values(),
        key=lambda item: (item['masuk'] is None, item['masuk'].waktu if item['masuk'] else None)
    )

    return render_template(
        "absensi.html",
        data_absensi=data_absensi_terurut,
        kelas_list=kelas_list,
        kelas_id=kelas_id,
        cari_nama=cari_nama
    )

@app.route("/update_absensi/<string:nis>", methods=["POST"])
def update_absensi(nis):
    """
    Rute untuk memperbarui status absensi siswa (Sakit/Izin/Alfa).
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    status = request.form.get("status")
    keterangan = request.form.get("keterangan")
    tanggal = datetime.today().date()
    kelas_id = request.form.get("kelas_id")
    cari_nama = request.form.get("cari_nama")

    if status and nis:
        existing_absensi = Absensi.query.filter(
            Absensi.nis == nis,
            Absensi.tanggal == tanggal,
            Absensi.jenis_absen.in_(["masuk", "lainnya"])
        ).first()

        if existing_absensi:
            existing_absensi.status = status
            existing_absensi.jenis_absen = "lainnya"
            if keterangan:
                existing_absensi.keterangan = keterangan
            flash(f"Status absensi untuk NIS {nis} berhasil diperbarui menjadi {status}.", "success")
        else:
            absen_baru = Absensi(
                nis=nis,
                tanggal=tanggal,
                status=status,
                keterangan=keterangan,
                jenis_absen="lainnya",
                waktu=datetime.now().time()
            )
            db.session.add(absen_baru)
            flash(f"Status absensi untuk NIS {nis} berhasil ditambahkan.", "success")

        db.session.commit()

    return redirect(url_for("absensi", kelas_id=kelas_id, cari_nama=cari_nama))


# =======================================================================
#  ROUTE: PENGATURAN UMUM
# =======================================================================
@app.route("/pengaturan", methods=["GET", "POST"])
def pengaturan():
    """
    Menampilkan halaman pengaturan dan mengelola semua sub-pengaturan.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    # Ambil data pengaturan waktu untuk ditampilkan
    setting = SettingWaktu.query.first()

    if request.method == "POST":
        # Logika untuk menyimpan pengaturan waktu
        jam_masuk_mulai = request.form.get("jam_masuk_mulai")
        jam_masuk_selesai = request.form.get("jam_masuk_selesai")
        jam_pulang_mulai = request.form.get("jam_pulang_mulai")
        jam_pulang_selesai = request.form.get("jam_pulang_selesai")
        jam_terlambat_selesai_str = request.form.get("jam_terlambat_selesai")

        # Validasi sederhana
        if not jam_masuk_mulai or not jam_masuk_selesai or not jam_pulang_mulai or not jam_pulang_selesai:
            flash("Semua waktu wajib (kecuali batas terlambat) harus diisi.", "danger")
            return redirect(url_for("pengaturan"))

        try:
            if not setting:
                setting = SettingWaktu()
                db.session.add(setting)

            setting.jam_masuk_mulai = datetime.strptime(jam_masuk_mulai, "%H:%M").time()
            setting.jam_masuk_selesai = datetime.strptime(jam_masuk_selesai, "%H:%M").time()
            setting.jam_pulang_mulai = datetime.strptime(jam_pulang_mulai, "%H:%M").time()
            setting.jam_pulang_selesai = datetime.strptime(jam_pulang_selesai, "%H:%M").time()

            if jam_terlambat_selesai_str:
                setting.jam_terlambat_selesai = datetime.strptime(jam_terlambat_selesai_str, "%H:%M").time()
            else:
                setting.jam_terlambat_selesai = None

            db.session.commit()
            flash("Pengaturan waktu berhasil disimpan", "success")
        except ValueError:
            flash("Format waktu tidak valid, silakan coba lagi.", "danger")

        return redirect(url_for("pengaturan"))

    return render_template("pengaturan.html", setting=setting)


@app.route("/reset_waktu")
def reset_waktu():
    """Menghapus pengaturan waktu absensi."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    setting = SettingWaktu.query.first()
    if setting:
        db.session.delete(setting)
        db.session.commit()
        flash("Pengaturan waktu berhasil direset", "success")
    else:
        flash("Pengaturan waktu belum pernah diatur", "warning")
    return redirect(url_for("pengaturan"))


# =======================================================================
#  ROUTE: EKSPOR LAPORAN EXCEL
# =======================================================================
def get_daily_attendance_data():
    """
    Mengambil data absensi harian dari database dengan JOIN tabel Absensi dan Siswa.
    Mengembalikan data dalam format list of dictionaries yang siap untuk Pandas.
    """
    today = datetime.today().date()

    # Ambil data absensi masuk dan pulang hari ini
    absensi_masuk = Absensi.query.filter(
        Absensi.tanggal == today,
        Absensi.jenis_absen == 'masuk'
    ).all()

    absensi_pulang = Absensi.query.filter(
        Absensi.tanggal == today,
        Absensi.jenis_absen == 'pulang'
    ).all()

    # Ambil semua data siswa untuk digabungkan (join)
    siswa_all = Siswa.query.all()

    # Buat dictionary untuk mempermudah pencarian
    siswa_dict = {s.nis: s for s in siswa_all}
    absensi_masuk_dict = {a.nis: a for a in absensi_masuk}
    absensi_pulang_dict = {a.nis: a for a in absensi_pulang}

    final_data = []

    # Gabungkan data
    for i, siswa in enumerate(siswa_all):
        nis = siswa.nis
        data_row = {
            'No': i + 1,
            'NIS': nis,
            'Nama Siswa': siswa.nama,
            'Kelas': siswa.kelas_relasi.nama if siswa.kelas_relasi else 'Tidak Diketahui',
            'Status Masuk': 'Alfa',
            'Waktu Masuk': '-',
            'Status Pulang': 'Alfa',
            'Waktu Pulang': '-'
        }

        # Cek data absensi masuk
        if nis in absensi_masuk_dict:
            absen = absensi_masuk_dict[nis]
            data_row['Status Masuk'] = absen.status
            data_row['Waktu Masuk'] = absen.waktu.strftime('%H:%M') if absen.waktu else '-'

        # Cek data absensi pulang
        if nis in absensi_pulang_dict:
            absen = absensi_pulang_dict[nis]
            data_row['Status Pulang'] = absen.status
            data_row['Waktu Pulang'] = absen.waktu.strftime('%H:%M') if absen.waktu else '-'

        final_data.append(data_row)

    return final_data


@app.route("/export_harian_excel")
def export_harian_excel():
    """
    Rute untuk mengekspor laporan absensi harian ke file Excel.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    data_absensi_harian = get_daily_attendance_data()

    # Buat DataFrame dari data
    df = pd.DataFrame(data_absensi_harian)

    # Siapkan file Excel di memori
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Harian')
    output.seek(0)

    # Kirim file sebagai respons
    nama_file = f"Laporan_Harian_{datetime.today().date().strftime('%Y-%m-%d')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nama_file
    )


@app.route("/export_laporan", methods=["GET", "POST"])
def export_laporan():
    """
    Menampilkan halaman untuk memilih bulan, tahun, dan kelas
    untuk ekspor laporan bulanan.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas_list = Kelas.query.order_by(Kelas.nama.asc()).all()
    now = datetime.now()
    default_bulan = now.strftime('%Y-%m')

    if request.method == "POST":
        bulan_pilih = request.form.get("bulan")
        kelas_pilih_id = request.form.get("kelas")

        if not bulan_pilih or not kelas_pilih_id:
            flash("Mohon pilih bulan dan kelas", "danger")
            return redirect(url_for("export_laporan"))

        return redirect(url_for("generate_excel", bulan=bulan_pilih, kelas_id=kelas_pilih_id))

    return render_template("export_laporan.html", kelas_list=kelas_list, default_bulan=default_bulan)


@app.route("/generate_excel/<bulan>/<kelas_id>")
def generate_excel(bulan, kelas_id):
    """
    Memproses dan menghasilkan file Excel dalam format pivot (crosstab).
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    try:
        tahun, bulan_int = map(int, bulan.split('-'))

        data = (
            db.session.query(
                Siswa.nama, Siswa.nis, Absensi.tanggal, Absensi.status
            )
            .join(Absensi, Siswa.nis == Absensi.nis)
            .filter(
                Siswa.kelas_id == kelas_id,
                db.extract('year', Absensi.tanggal) == tahun,
                db.extract('month', Absensi.tanggal) == bulan_int
            )
            .all()
        )

        kelas_obj = Kelas.query.get(kelas_id)
        nama_kelas = kelas_obj.nama if kelas_obj else "Tidak Diketahui"

        if not data:
            flash(f"Tidak ada data absensi untuk kelas {nama_kelas} di bulan ini", "warning")
            return redirect(url_for("export_laporan"))

        df = pd.DataFrame(data, columns=["Nama", "NIS", "Tanggal", "Status"])

        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        df['Hari'] = df['Tanggal'].dt.strftime('%d')

        df['Tampilan Status'] = df['Status'].apply(lambda s: 'H' if s in ['Hadir', 'Terlambat'] else s[0].upper())

        df_pivot = pd.pivot_table(
            df,
            values='Tampilan Status',
            index=['Nama', 'NIS'],
            columns='Hari',
            aggfunc='first'
        )

        df_pivot.reset_index(inplace=True)

        total_hadir = df.groupby(['Nama', 'NIS'])['Tampilan Status'].apply(
            lambda x: (x == 'H').sum()
        ).reset_index(name='Total Hadir')

        total_terlambat = df.groupby(['Nama', 'NIS'])['Status'].apply(
            lambda x: (x == 'Terlambat').sum()
        ).reset_index(name='Total Terlambat')

        df_final = pd.merge(df_pivot, total_hadir, on=['Nama', 'NIS'])
        df_final = pd.merge(df_final, total_terlambat, on=['Nama', 'NIS'])

        kolom_hari = [str(d).zfill(2) for d in range(1, 32)]
        kolom_final = ['NIS', 'Nama'] + [c for c in kolom_hari if c in df_final.columns] + ['Total Hadir',
                                                                                            'Total Terlambat']
        df_final = df_final[kolom_final]

        df_final.fillna('-', inplace=True)

        file_path = f"Laporan_Absensi_{nama_kelas}_{bulan}.xlsx"
        df_final.to_excel(file_path, index=False)

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        print(f"Error saat membuat file Excel: {e}")
        flash("Terjadi kesalahan saat membuat laporan. Silakan coba lagi.", "danger")
        return redirect(url_for("export_laporan"))

# =======================================================================
#  MAIN EXECUTION
# =======================================================================
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")