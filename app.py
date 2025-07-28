from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
from flask_cors import CORS
import logging
from google.cloud import firestore
from datetime import datetime, timedelta
import pytz

# Khởi tạo Flask app
app = Flask(__name__)
CORS(app)

# Cấu hình logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("LicenseAPI")

# Khởi tạo Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def get_license_doc(key):
    """Lấy document license từ Firestore"""
    doc_ref = db.collection('licenses').document(key)
    doc = doc_ref.get()
    return doc_ref, doc.to_dict() if doc.exists else None

@app.route('/wakeup', methods=['GET'])
def wakeup():
    """Endpoint đánh thức server"""
    return jsonify({"status": "active", "message": "Server is ready"}), 200

@app.route('/activate', methods=['POST'])
def activate_key():
    try:
        data = request.json
        key = data.get('key')
        hardware_id = data.get('hardware_id')

        # Validate input
        if not key or len(key) != 12 or not key.isdigit():
            return jsonify({"success": False, "error": "Mã kích hoạt phải có đúng 12 chữ số"}), 400
            
        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Mã kích hoạt không tồn tại"}), 404

        now = datetime.now(pytz.UTC)
        
        # Xử lý license đã kích hoạt
        if license_data.get('activated_at'):
            # Chuyển đổi tất cả datetime/timestamp về string ISO format
            expires_at = license_data['expires_at']
            activated_at = license_data['activated_at']
            
            # Nếu là Firestore Timestamp
            if hasattr(expires_at, 'isoformat'):
                expires_at = expires_at.isoformat()
            elif hasattr(expires_at, 'strftime'):
                expires_at = expires_at.strftime('%Y-%m-%dT%H:%M:%S%z')
                
            if hasattr(activated_at, 'isoformat'):
                activated_at = activated_at.isoformat()
            elif hasattr(activated_at, 'strftime'):
                activated_at = activated_at.strftime('%Y-%m-%dT%H:%M:%S%z')

            if license_data['hardware_id'] != hardware_id:
                return jsonify({
                    "success": False, 
                    "error": "Mã này đã được kích hoạt trên thiết bị khác",
                    "expires_at": expires_at,
                    "activated_at": activated_at
                }), 403
            
            return jsonify({
                "success": True,
                "license_type": license_data['license_type'],
                "expires_at": expires_at,
                "activated_at": activated_at
            }), 200
        
        # Xử lý license mới
        if license_data.get('license_type') == 'lifetime':
            expires_at = "9999-12-31T23:59:59+00:00"
        else:
            duration_days = int(license_data.get('duration_days', 0))
            expires_at = (now + timedelta(days=duration_days)).isoformat()

        # Cập nhật Firestore - sử dụng firestore.SERVER_TIMESTAMP cho thời gian
        update_data = {
            'hardware_id': hardware_id,
            'activated_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at
        }
        doc_ref.update(update_data)
        
        return jsonify({
            "success": True,
            "license_type": license_data['license_type'],
            "expires_at": expires_at,
            "activated_at': now.isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Lỗi kích hoạt: {str(e)}", exc_info=True)
        return jsonify({
            "success": False, 
            "error": "Lỗi hệ thống",
            "details": str(e)
        }), 500

@app.route('/verify', methods=['POST'])
def verify_key():
    """Endpoint xác thực license"""
    try:
        data = request.json
        key = data.get('key')
        hardware_id = data.get('hardware_id')

        if not key or not hardware_id:
            return jsonify({"valid": False, "message": "Thiếu thông tin key hoặc hardware_id"}), 400

        _, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"valid": False, "message": "Key không hợp lệ"}), 404

        # Kiểm tra hardware_id
        if license_data.get('hardware_id') != hardware_id:
            return jsonify({
                "valid": False, 
                "message": "Key đã được sử dụng trên thiết bị khác"
            }), 403

        now = datetime.now(pytz.UTC)
        
        # License vĩnh viễn
        if license_data.get('license_type') == 'lifetime':
            return jsonify({
                "valid": True,
                "license_type": "lifetime",
                "expires_at": license_data['expires_at']
            }), 200

        # Kiểm tra thời hạn
        expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
        if expires_at < now:
            return jsonify({
                "valid": False, 
                "message": "License đã hết hạn",
                "expired_date": expires_at.strftime('%d/%m/%Y')
            }), 403

        return jsonify({
            "valid": True,
            "license_type": license_data['license_type'],
            "expires_at": license_data['expires_at']
        }), 200

    except Exception as e:
        logger.error("Lỗi xác thực: %s", str(e), exc_info=True)
        return jsonify({
            "valid": False, 
            "message": "Lỗi hệ thống"
        }), 500

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "running",
        "endpoints": {
            "activate": "/activate (POST)",
            "verify": "/verify (POST)",
            "wakeup": "/wakeup (GET)"
        }
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
