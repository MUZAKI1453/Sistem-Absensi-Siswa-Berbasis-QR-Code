# ======================== IMPORTS & SETUP APLIKASI ========================
import os
import qrcode
import pandas as pd
import requests
from datetime import datetime
from sqlalchemy import and_
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    jsonify,
    send_from_directory,
    flash
)
from PIL import Image, ImageDraw, ImageFont
from models import db, Siswa, Absensi, SettingWaktu
import io

app = Flask(__name__)
app.secret_key = "absensi_qr_secret"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///absensi.db'
app.config['UPLOAD_FOLDER'] = 'static/qr_codes'
db.init_app(app)

with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ======================== FUNGSI HELPER ========================
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
    text_nis  = nis

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


# ======================== AUTENTIKASI ADMIN ========================
@app.route("/", methods=["GET", "POST"])
def login():
    """Rute untuk halaman login admin."""
    if request.method == "POST":
        # Peringatan: Gunakan metode autentikasi yang lebih aman di lingkungan produksi
        if request.form["username"] == "admin" and request.form["password"] == "123":
            session["admin"] = True
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Username atau password salah.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Rute untuk logout, menghapus session admin."""
    session.clear()
    return redirect(url_for("login"))


# ======================== DASHBOARD ========================
@app.route("/dashboard")
def dashboard():
    """Menampilkan dashboard dengan statistik absensi hari ini."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    hari_ini = datetime.today().date()

    total_siswa = Siswa.query.count()
    total_kelas = Siswa.query.with_entities(Siswa.kelas).distinct().count()

    total_hadir = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.status == "Hadir",
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
        total_sakit=total_sakit,
        total_izin=total_izin,
        total_alfa=total_alfa,
        total_siswa=total_siswa,
        total_kelas=total_kelas
    )


# ======================== KELOLA SISWA (CRUD) ========================
@app.route("/siswa", methods=["GET", "POST"])
def siswa():
    """
    Mengelola data siswa.
    - GET: Menampilkan daftar siswa.
    - POST: Menambah atau mengupdate data siswa.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    siswa_edit = None
    edit_id = request.args.get("edit_id")
    if edit_id:
        siswa_edit = Siswa.query.get(edit_id)

    if request.method == "POST":
        nis = request.form["nis"]
        nama = request.form["nama"]
        kelas = request.form["kelas"]
        no_hp = request.form["no_hp"]

        if siswa_edit:
            nis_lain = Siswa.query.filter(Siswa.nis == nis, Siswa.id != siswa_edit.id).first()
            if nis_lain:
                flash(f"NIS {nis} sudah digunakan oleh siswa lain.", "danger")
                return redirect(url_for("siswa", edit_id=siswa_edit.id))

            siswa_edit.nis = nis
            siswa_edit.nama = nama
            siswa_edit.kelas = kelas
            siswa_edit.no_hp_ortu = no_hp

            qr_filename = f"{nis}.png"
            qr_path = os.path.join(app.config['UPLOAD_FOLDER'], qr_filename)
            qr_image = create_qr_with_text(nis, nama)
            qr_image.save(qr_path)
            siswa_edit.qr_path = qr_path

            db.session.commit()
            flash("Data siswa berhasil diperbarui", "success")
        else:
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
                kelas=kelas,
                no_hp_ortu=no_hp,
                qr_path=qr_path
            )
            db.session.add(siswa_baru)
            db.session.commit()
            flash("Data siswa berhasil ditambahkan", "success")

        return redirect(url_for("siswa"))

    else:
        cari_nama = request.args.get("cari_nama")
        filter_kelas = request.args.get("filter_kelas")

        query = Siswa.query

        if cari_nama:
            query = query.filter(Siswa.nama.ilike(f"%{cari_nama}%"))

        if filter_kelas:
            query = query.filter(Siswa.kelas == filter_kelas)

        data_siswa = query.order_by(Siswa.nama.asc()).all()

        semua_kelas = [k[0] for k in db.session.query(Siswa.kelas).distinct().order_by(Siswa.kelas).all()]

        return render_template("siswa.html",
                               siswa=data_siswa,
                               siswa_edit=siswa_edit,
                               cari_nama=cari_nama,
                               filter_kelas=filter_kelas,
                               semua_kelas=semua_kelas)


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


# ======================== PROSES ABSENSI & SCANNER ========================
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
    if setting.jam_masuk_mulai <= waktu_skrg <= setting.jam_masuk_selesai:
        jenis_absen = "masuk"
    elif setting.jam_pulang_mulai <= waktu_skrg <= setting.jam_pulang_selesai:
        jenis_absen = "pulang"
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
        status="Hadir",
        jenis_absen=jenis_absen,
        tanggal=hari_ini,
        waktu=now.time()
    )
    db.session.add(absensi)
    db.session.commit()

    nomor = format_nomor_hp(siswa.no_hp_ortu)
    pesan = f"Siswa {siswa.nama} ({siswa.nis}) telah absen {jenis_absen} pada {now.strftime('%H:%M')}"

    try:
        # PENTING: Ganti token ini dengan token Fonnte Anda yang valid
        # Jika tidak ada, fitur notifikasi WA tidak akan berfungsi
        FONNTE_TOKEN = "m7sWNBLHrGi2AHZNj2x3"
        url = "https://api.fonnte.com/send"
        headers = {"Authorization": FONNTE_TOKEN}
        data = {"target": nomor, "message": pesan}
        response = requests.post(url, headers=headers, data=data)

        if response.status_code == 200:
            return jsonify({
                'status': 'success',
                'message': f"Absen {jenis_absen} berhasil & WA terkirim"
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': f"Absen {jenis_absen} berhasil, tapi notifikasi WA gagal. Kode: {response.status_code}"
            })
    except Exception as e:
        return jsonify({
            'status': 'warning',
            'message': f"Absen {jenis_absen} berhasil, tapi notifikasi WA gagal: {str(e)}"
        })


# ======================== KELOLA ABSENSI ========================
@app.route("/absensi", methods=["GET"])
def absensi():
    """
    Menampilkan data absensi harian dan memungkinkan filter per kelas.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    hari_ini = datetime.today().date()
    kelas_list = [k[0] for k in db.session.query(Siswa.kelas).distinct().order_by(Siswa.kelas).all()]
    kelas = request.args.get("kelas")

    siswa_query = Siswa.query
    if kelas:
        siswa_query = siswa_query.filter_by(kelas=kelas)
    semua_siswa = siswa_query.order_by(Siswa.nama.asc()).all()

    nis_list = [s.nis for s in semua_siswa]
    absensi_hari_ini = Absensi.query.filter(
        Absensi.tanggal == hari_ini,
        Absensi.nis.in_(nis_list)
    ).all()

    data_absensi = {}
    for siswa in semua_siswa:
        data_absensi[siswa.nis] = {
            "siswa": siswa,
            "masuk": None,
            "pulang": None
        }

    for absen in absensi_hari_ini:
        if absen.jenis_absen == 'lainnya':
            data_absensi[absen.nis]['masuk'] = absen
            data_absensi[absen.nis]['pulang'] = absen
        elif absen.jenis_absen == 'masuk':
            data_absensi[absen.nis]['masuk'] = absen
        elif absen.jenis_absen == 'pulang':
            data_absensi[absen.nis]['pulang'] = absen

    return render_template(
        "absensi.html",
        data_absensi=data_absensi,
        kelas_list=kelas_list,
        kelas=kelas
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

    if status and nis:
        existing_absensi = Absensi.query.filter(
            Absensi.nis == nis,
            Absensi.tanggal == tanggal
        ).first()

        if existing_absensi:
            existing_absensi.status = status
            existing_absensi.keterangan = keterangan
            existing_absensi.jenis_absen = "lainnya"
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

    return redirect(url_for("absensi", kelas=request.args.get("kelas")))


def get_badge_color(status):
    if status == 'Hadir':
        return 'success'
    elif status == 'Izin':
        return 'warning text-dark'
    elif status == 'Sakit':
        return 'info text-dark'
    else:
        return 'danger'


app.jinja_env.filters['get_badge_color'] = get_badge_color


# ======================== PENGATURAN WAKTU ========================
@app.route("/atur_waktu", methods=["GET", "POST"])
def atur_waktu():
    """Mengelola pengaturan waktu untuk absensi masuk dan pulang."""
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    if request.method == "POST":
        jam_masuk_mulai = request.form["jam_masuk_mulai"]
        jam_masuk_selesai = request.form["jam_masuk_selesai"]
        jam_pulang_mulai = request.form["jam_pulang_mulai"]
        jam_pulang_selesai = request.form["jam_pulang_selesai"]

        setting = SettingWaktu.query.first()
        if not setting:
            setting = SettingWaktu()
            db.session.add(setting)

        setting.jam_masuk_mulai = datetime.strptime(jam_masuk_mulai, "%H:%M").time()
        setting.jam_masuk_selesai = datetime.strptime(jam_masuk_selesai, "%H:%M").time()
        setting.jam_pulang_mulai = datetime.strptime(jam_pulang_mulai, "%H:%M").time()
        setting.jam_pulang_selesai = datetime.strptime(jam_pulang_selesai, "%H:%M").time()

        db.session.commit()
        flash("Pengaturan waktu berhasil disimpan", "success")
        return redirect(url_for("atur_waktu"))

    setting = SettingWaktu.query.first()
    return render_template("atur_waktu.html", setting=setting)


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
    return redirect(url_for("atur_waktu"))


# ======================== EKSPOR LAPORAN EXCEL ========================
@app.route("/export_laporan", methods=["GET", "POST"])
def export_laporan():
    """
    Menampilkan halaman untuk memilih bulan, tahun, dan kelas
    untuk ekspor laporan bulanan.
    """
    auth_check = check_admin_session()
    if auth_check:
        return auth_check

    kelas_list = [k[0] for k in db.session.query(Siswa.kelas).distinct().order_by(Siswa.kelas).all()]

    now = datetime.now()
    default_bulan = now.strftime('%Y-%m')

    if request.method == "POST":
        bulan_pilih = request.form.get("bulan")
        kelas_pilih = request.form.get("kelas")

        if not bulan_pilih or not kelas_pilih:
            flash("Mohon pilih bulan dan kelas", "danger")
            return redirect(url_for("export_laporan"))

        return redirect(url_for("generate_excel", bulan=bulan_pilih, kelas=kelas_pilih))

    return render_template("export_laporan.html", kelas_list=kelas_list, default_bulan=default_bulan)


@app.route("/generate_excel/<bulan>/<kelas>")
def generate_excel(bulan, kelas):
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
                Siswa.kelas == kelas,
                db.extract('year', Absensi.tanggal) == tahun,
                db.extract('month', Absensi.tanggal) == bulan_int
            )
            .all()
        )

        if not data:
            flash(f"Tidak ada data absensi untuk kelas {kelas} di bulan ini", "warning")
            return redirect(url_for("export_laporan"))

        df = pd.DataFrame(data, columns=["Nama", "NIS", "Tanggal", "Status"])

        df['Tanggal'] = pd.to_datetime(df['Tanggal'])
        df['Hari'] = df['Tanggal'].dt.strftime('%d')

        df['Status'] = df['Status'].apply(lambda s: s[0].upper())

        df_pivot = pd.pivot_table(
            df,
            values='Status',
            index=['Nama', 'NIS'],
            columns='Hari',
            aggfunc='first'
        )

        df_pivot.reset_index(inplace=True)

        total_hadir = df.groupby(['Nama', 'NIS'])['Status'].apply(
            lambda x: (x == 'H').sum()
        ).reset_index(name='Total Hadir')

        df_final = pd.merge(df_pivot, total_hadir, on=['Nama', 'NIS'])

        kolom_hari = [str(d).zfill(2) for d in range(1, 32)]
        kolom_final = ['NIS', 'Nama'] + [c for c in kolom_hari if c in df_final.columns] + ['Total Hadir']
        df_final = df_final[kolom_final]

        df_final.fillna('-', inplace=True)

        file_path = f"Laporan_Absensi_{kelas}_{bulan}.xlsx"
        df_final.to_excel(file_path, index=False)

        return send_file(file_path, as_attachment=True)

    except Exception as e:
        print(f"Error saat membuat file Excel: {e}")
        flash("Terjadi kesalahan saat membuat laporan. Silakan coba lagi.", "danger")
        return redirect(url_for("export_laporan"))


# ======================== MAIN ========================
if __name__ == "__main__":
    # Jalankan aplikasi Flask
    app.run(debug=True, host="0.0.0.0")
