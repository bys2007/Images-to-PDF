from flask import Flask, request, send_file, render_template, jsonify
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import io
import base64

app = Flask(__name__)

# Fungsi efek Scan
def apply_scan_effect(image):
    # Konversi gambar ke grayscale
    gray_image = image.convert("L")
    
    # Tingkatkan kontras
    enhancer = ImageEnhance.Contrast(gray_image)
    enhanced = enhancer.enhance(2.0)

    # Terapkan filter edge-enhance
    scanned_effect = enhanced.filter(ImageFilter.EDGE_ENHANCE)
    return scanned_effect

def apply_compression(image, mode, manual_quality=None, is_grayscale=False):
    mode = (mode or "none").lower()
    if mode not in {"none", "best", "manual", "max"}:
        mode = "none"

    if mode == "none":
        return image

    target_mode = "L" if is_grayscale else "RGB"
    working_image = image.convert(target_mode)
    width, height = working_image.size

    if mode == "best":
        max_width = 2200
        quality = 82
    elif mode == "manual":
        max_width = width
        quality = manual_quality if manual_quality is not None else 80
    elif mode == "max":
        max_width = 1400
        quality = 60
    else:
        max_width = width
        quality = 92

    if is_grayscale and mode in {"best", "max"}:
        quality = max(40, quality - 8)

    if mode == "manual" and manual_quality is not None:
        quality = manual_quality

    quality = int(max(30, min(95, quality)))

    if max_width and width > max_width:
        scale = max_width / float(width)
        new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
        working_image = working_image.resize(new_size, Image.LANCZOS)

    buffer = io.BytesIO()
    working_image.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    compressed_image = Image.open(buffer)
    compressed_image.load()
    buffer.close()

    if is_grayscale:
        compressed_image = compressed_image.convert("L")
    else:
        compressed_image = compressed_image.convert("RGB")
    return compressed_image

def apply_effect(image, effect):
    effect = (effect or "color").lower()
    if effect == "bw":
        return image.convert("L")
    if effect == "scan":
        return apply_scan_effect(image)
    return image

def sanitize_compression_input(mode, manual_quality):
    mode = (mode or "none").lower()
    if mode not in {"none", "best", "manual", "max"}:
        mode = "none"

    try:
        manual_quality = int(manual_quality) if manual_quality is not None else None
    except (TypeError, ValueError):
        manual_quality = None

    if manual_quality is not None:
        manual_quality = max(30, min(95, manual_quality))

    return mode, manual_quality

def prepare_image(image, effect, compression_mode, manual_quality):
    image = ImageOps.exif_transpose(image)
    image = apply_effect(image, effect)
    is_grayscale = image.mode == "L"
    image = apply_compression(image, compression_mode, manual_quality, is_grayscale=is_grayscale)
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_to_pdf():
    images = []
    compression_mode = "none"
    manual_quality = None

    content_type = request.content_type or ""
    is_json = "application/json" in content_type

    if is_json:
        payload = request.get_json(silent=True) or {}
        images_data = payload.get("images", [])
        compression_data = payload.get("compression", {}) or {}
        compression_mode, manual_quality = sanitize_compression_input(
            compression_data.get("mode"),
            compression_data.get("quality")
        )

        if not images_data:
            return jsonify({"error": "Tidak ada gambar yang dikirim."}), 400

        for index, img_data in enumerate(images_data):
            try:
                img_str = img_data["src"].split(",")[1]
            except (KeyError, IndexError, AttributeError):
                return jsonify({"error": f"Format data gambar tidak valid pada indeks {index}."}), 400
            effect = img_data.get("effect", "color")
            try:
                decoded = base64.b64decode(img_str)
            except (base64.binascii.Error, ValueError):
                return jsonify({"error": f"Gagal mendekode gambar pada indeks {index}."}), 400

            with Image.open(io.BytesIO(decoded)) as img:
                processed = prepare_image(img, effect, compression_mode, manual_quality)
            images.append(processed)
    else:
        files = request.files.getlist("files")
        effects = request.form.getlist("effects")
        compression_mode, manual_quality = sanitize_compression_input(
            request.form.get("compressionMode"),
            request.form.get("manualQuality")
        )

        if not files:
            return jsonify({"error": "Tidak ada gambar yang dikirim."}), 400

        for index, file_storage in enumerate(files):
            effect = effects[index] if index < len(effects) else "color"
            try:
                with Image.open(file_storage.stream) as img_source:
                    processed = prepare_image(img_source, effect, compression_mode, manual_quality)
            except Exception:
                return jsonify({"error": f"Gagal membaca file gambar pada indeks {index}."}), 400
            images.append(processed)

    # Simpan ke PDF
    pdf_bytes = io.BytesIO()
    pdf_info = {
        "Author": "bys",
        "Creator": "bys Image to PDF Converter",
        "Producer": "bys",
    }
    images[0].save(
        pdf_bytes,
        format="PDF",
        save_all=True,
        append_images=images[1:],
        pdfinfo=pdf_info
    )
    pdf_bytes.seek(0)

    return send_file(pdf_bytes, mimetype='application/pdf', as_attachment=True, download_name='output.pdf')

if __name__ == '__main__':
    app.run(debug=True)
