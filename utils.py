import qrcode
from PIL import Image, ImageDraw, ImageFont
from flask import session, redirect, url_for, flash

import requests
from datetime import date
from models import db, Siswa, Absensi, HariLibur

def check_admin_session():
    """Periksa apakah admin sudah login."""
    if "admin" not in session:
        flash("Silakan login terlebih dahulu.", "warning")
        return redirect(url_for("login"))  # arahkan ke route login utama
    return None


def format_nomor_hp(nomor):
    """Format nomor HP ke format internasional (62...)."""
    nomor = nomor.strip()
    return "62" + nomor[1:] if nomor.startswith("0") else nomor[1:] if nomor.startswith("+62") else nomor


def create_qr_siswa(nis, nama):
    """Buat QR code untuk Siswa dengan teks di bawahnya rata tengah."""
    data_qr = f"S{nis}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Font
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    # Dua baris teks (nama dan NIS)
    text_lines = [nama, str(nis)]
    line_spacing = 5  # jarak antar baris
    padding_top = 1  # jarak antara QR dan teks

    # Hitung ukuran teks total
    draw_tmp = ImageDraw.Draw(qr_img)
    text_w = max(draw_tmp.textlength(line, font=font) for line in text_lines)
    text_h = sum(font.getbbox(line)[3] - font.getbbox(line)[1] for line in text_lines) + line_spacing

    # Buat kanvas baru dengan ruang tambahan di bawah QR
    margin_bottom = 20
    new_height = qr_img.height + text_h + padding_top + margin_bottom
    new_img = Image.new("RGB", (qr_img.width, new_height), "white")
    new_img.paste(qr_img, (0, 0))

    # Gambar teks, rata tengah
    draw = ImageDraw.Draw(new_img)
    current_y = qr_img.height + padding_top
    for line in text_lines:
        line_w = draw.textlength(line, font=font)
        text_x = (new_img.width - line_w) // 2
        draw.text((text_x, current_y), line, fill="black", font=font)
        current_y += font.getbbox(line)[3] - font.getbbox(line)[1] + line_spacing

    return new_img


def create_qr_pegawai(no_id, nama, role):
    """Buat QR code untuk Pegawai dengan teks di bawahnya rata tengah dan tidak terpotong."""
    data_qr = f"P{no_id}"
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Pilih font
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    # Hitung tinggi total teks
    line_spacing = 5
    text_lines = [nama, role]
    draw_tmp = ImageDraw.Draw(qr_img)
    text_w = max(draw_tmp.textlength(line, font=font) for line in text_lines)
    text_h = sum(font.getbbox(line)[3] - font.getbbox(line)[1] for line in text_lines) + line_spacing

    # Tambahkan margin bawah agar teks tidak kepotong
    padding_top = 1  # jarak antara QR dan teks
    margin_bottom = 20  # ruang ekstra di bawah teks

    new_height = qr_img.height + text_h + padding_top + margin_bottom
    new_img = Image.new("RGB", (qr_img.width, new_height), "white")
    new_img.paste(qr_img, (0, 0))

    # Gambar teks rata tengah
    draw = ImageDraw.Draw(new_img)
    current_y = qr_img.height + padding_top
    for line in text_lines:
        line_w = draw.textlength(line, font=font)
        text_x = (new_img.width - line_w) // 2
        draw.text((text_x, current_y), line, fill="black", font=font)
        current_y += font.getbbox(line)[3] - font.getbbox(line)[1] + line_spacing

    return new_img


# Token Fonnte WA Gateway
FONNTE_TOKEN = "m7sWNBLHrGi2AHZNj2x3"  # ganti dengan token kamu


def kirim_pesan_wa(target, message):
    """Mengirim pesan WhatsApp menggunakan Fonnte API."""
    try:
        response = requests.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN},
            data={"target": target, "message": message}
        )
        if response.status_code == 200:
            print(f"✅ Pesan WA terkirim ke {target}")
        else:
            print(f"⚠️ Gagal kirim WA ke {target}: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error kirim WA ke {target}: {e}")


def kirim_notifikasi_terlambat(app):
    """Kirim WA ke orang tua siswa yang belum absen setelah waktu terlambat selesai."""
    with app.app_context():
        print("🚀 Mengecek siswa yang belum absen...")

        today = date.today()

        # Cek hari libur
        libur = HariLibur.query.filter_by(tanggal=today).first()
        if libur:
            print(f"⛱️ Hari ini libur: {libur.keterangan}")
            return

        siswa_list = Siswa.query.all()
        absen_hari_ini = [a.nis for a in Absensi.query.filter_by(tanggal=today).all()]
        belum_absen = [s for s in siswa_list if s.nis not in absen_hari_ini]

        if not belum_absen:
            print("✅ Semua siswa sudah absen hari ini.")
            return

        link_izin = "http://127.0.0.1:8080/izin/"

        for s in belum_absen:
            if s.no_hp_ortu:
                nomor = format_nomor_hp(s.no_hp_ortu)
                pesan = (
                    f"📚 *Notifikasi Absensi Sekolah*\n\n"
                    f"Halo, orang tua dari *{s.nama}*.\n\n"
                    f"Hingga batas waktu absensi berakhir hari ini ({today}), "
                    "putra/putri Anda *belum tercatat melakukan absensi* di sekolah.\n\n"
                    "Mohon konfirmasi kehadiran Jika anak Anda sedang sakit atau izin, "
                    "silakan ajukan keterangan melalui tautan berikut:\n"
                    f"{link_izin}\n\n"
                    "Terima kasih 🙏"
                )
                kirim_pesan_wa(nomor, pesan)
                print(f"📨 WA dikirim ke orang tua {s.nama} ({nomor})")

        print("✅ Semua notifikasi terlambat sudah dikirim.")