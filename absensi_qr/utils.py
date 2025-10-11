import qrcode
from PIL import Image, ImageDraw, ImageFont
from flask import session, redirect, url_for, flash


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
    """Buat QR code untuk Siswa dengan data prefiks 'S'."""
    data_qr = f"S{nis}"  # Data QR yang baru
    text = f"{nama}\nNIS: {nis}"

    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    draw_tmp = ImageDraw.Draw(qr_img)
    bbox = draw_tmp.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    new_img = Image.new("RGB", (qr_img.width, qr_img.height + text_h + 10), "white")
    new_img.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(new_img)
    text_x = (new_img.width - text_w) // 2
    text_y = qr_img.height + 5
    draw.text((text_x, text_y), text, fill="black", font=font)

    return new_img


def create_qr_pegawai(no_id, nama, role):
    """Buat QR code untuk Pegawai dengan data prefiks 'P'."""
    data_qr = f"P{no_id}"  # Data QR yang baru
    text = f"{nama}\nID: {no_id} ({role})"

    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(data_qr)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    draw_tmp = ImageDraw.Draw(qr_img)
    bbox = draw_tmp.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    new_img = Image.new("RGB", (qr_img.width, qr_img.height + text_h + 10), "white")
    new_img.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(new_img)
    text_x = (new_img.width - text_w) // 2
    text_y = qr_img.height + 5
    draw.text((text_x, text_y), text, fill="black", font=font)

    return new_img
