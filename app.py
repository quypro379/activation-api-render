from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import pytz

app = Flask(__name__)

# ✅ Khởi tạo Firestore
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_license_doc(key):
    doc_ref = db.collection('licenses').document(key)
    doc = doc_ref.get()
    return doc_ref, doc.to_dict() if doc.exists else None

@app.route('/wakeup', methods=['GET'])
def wakeup():
    return jsonify({"status": "ok", "message": "Server is awake"}), 200

@app.route('/activate', methods=['POST'])
def activate_key():
    try:
        data = request.json
        key = data.get('key')
        hardware_id = data.get('hardware_id')

        if not key or not hardware_id:
            return jsonify({"success": False, "error": "Thiếu key hoặc hardware_id"}), 400

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Key không hợp lệ"}), 404

        now = datetime.utcnow().replace(tzinfo=pytz.UTC)
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)

        # Kiểm tra hết hạn
        if expires_at < now:
            return jsonify({"success": False, "error": "Key đã hết hạn"}), 403

        # Kiểm tra hardware_id
        if license_data['hardware_id'] and license_data['hardware_id'] != hardware_id:
            return jsonify({"success": False, "error": "Key này đã được kích hoạt trên máy khác"}), 403

        # Ghi nhận hardware_id nếu chưa có
        if not license_data['hardware_id']:
            doc_ref.update({
                "hardware_id": hardware_id,
                "activated_at": firestore.SERVER_TIMESTAMP
            })

        return jsonify({
            "success": True,
            "license_type": license_data['license_type'],
            "expires_at": license_data['expires_at']
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/verify', methods=['POST'])
def verify_key():
    try:
        data = request.json
        key = data.get('key')
        hardware_id = data.get('hardware_id')

        if not key or not hardware_id:
            return jsonify({"valid": False, "message": "Thiếu key hoặc hardware_id"}), 400

        _, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"valid": False, "message": "Key không hợp lệ"}), 404

        # So khớp hardware_id
        if license_data['hardware_id'] and license_data['hardware_id'] != hardware_id:
            return jsonify({"valid": False, "message": "Key này đã dùng cho máy khác"}), 403

        now = datetime.utcnow().replace(tzinfo=pytz.UTC)
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)

        if expires_at < now:
            return jsonify({"valid": False, "message": "Key đã hết hạn"}), 403

        return jsonify({
            "valid": True,
            "license_type": license_data['license_type'],
            "expires_at": license_data['expires_at']
        }), 200
    except Exception as e:
        return jsonify({"valid": False, "message": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({"message": "API is running"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

