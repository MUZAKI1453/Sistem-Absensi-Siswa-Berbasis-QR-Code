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
