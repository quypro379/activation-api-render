from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta  # Thêm timedelta vào import
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

        # Kiểm tra nếu key đã được kích hoạt
        if license_data.get('activated_at'):
            # Nếu đã kích hoạt rồi thì kiểm tra hardware_id
            if license_data['hardware_id'] != hardware_id:
                return jsonify({"success": False, "error": "Key này đã được kích hoạt trên máy khác"}), 403
            
            # Nếu là license vĩnh viễn
            if license_data.get('license_type') == 'lifetime':
                return jsonify({
                    "success": True,
                    "license_type": "lifetime",
                    "expires_at": license_data['expires_at'],
                    "activated_at": license_data['activated_at']
                }), 200
            
            # Tính thời gian còn lại từ lần kích hoạt đầu tiên
            activated_at = datetime.fromisoformat(license_data['activated_at']).replace(tzinfo=pytz.UTC)
            expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
            
            # Thời gian còn lại = expires_at - (now - activated_at)
            remaining = expires_at - (datetime.utcnow().replace(tzinfo=pytz.UTC) - activated_at)
            
            return jsonify({
                "success": True,
                "license_type": license_data['license_type'],
                "expires_at": (datetime.utcnow().replace(tzinfo=pytz.UTC) + remaining).isoformat(),
                "activated_at": license_data['activated_at']
            }), 200
        else:
            # Nếu chưa kích hoạt thì tạo mới thời gian
            now = datetime.utcnow().replace(tzinfo=pytz.UTC)
            
            # Xử lý license vĩnh viễn
            if license_data.get('license_type') == 'lifetime':
                expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
            else:
                expires_at = now + timedelta(days=license_data['duration_days'])
            
            # Cập nhật thời gian kích hoạt và hết hạn
            doc_ref.update({
                "hardware_id": hardware_id,
                "activated_at": now.isoformat(),
                "expires_at": expires_at.isoformat()
            })
            
            return jsonify({
                "success": True,
                "license_type": license_data['license_type'],
                "expires_at": expires_at.isoformat(),
                "activated_at": now.isoformat()
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

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"valid": False, "message": "Key không hợp lệ"}), 404

        # Kiểm tra hardware_id khớp
        if license_data.get('hardware_id') != hardware_id:
            return jsonify({"valid": False, "message": "Key đã dùng trên máy khác"}), 403

        # Kiểm tra thời hạn
        now = datetime.now(pytz.UTC)
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
        
        if expires_at < now and license_data.get('license_type') != 'lifetime':
            return jsonify({"valid": False, "message": f"Key hết hạn từ {expires_at.strftime('%d/%m/%Y')}"}), 403

        return jsonify({
            "valid": True,
            "license_type": license_data.get('license_type'),
            "expires_at": license_data['expires_at']
        }), 200

    except Exception as e:
        return jsonify({"valid": False, "message": f"Lỗi server: {str(e)}"}), 500
