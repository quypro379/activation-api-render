from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import pytz
from flask_cors import CORS
import logging

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
    """Endpoint kích hoạt license key"""
    try:
        logger.debug("Nhận yêu cầu kích hoạt: %s", request.json)
        
        data = request.json
        key = data.get('key')
        hardware_id = data.get('hardware_id')

        # Validate input
        if not key or len(key) != 12 or not key.isdigit():
            return jsonify({"success": False, "error": "Mã kích hoạt phải có đúng 12 chữ số"}), 400
            
        if not hardware_id:
            return jsonify({"success": False, "error": "Thiếu hardware_id"}), 400

        doc_ref, license_data = get_license_doc(key)
        if not license_data:
            return jsonify({"success": False, "error": "Mã kích hoạt không tồn tại"}), 404

        now = datetime.now(pytz.UTC)
        
        # Xử lý license đã kích hoạt trước đó
        if license_data.get('activated_at'):
            if license_data['hardware_id'] != hardware_id:
                return jsonify({
                    "success": False, 
                    "error": "Mã này đã được kích hoạt trên thiết bị khác",
                    "solution": "Liên hệ hỗ trợ nếu bạn cần chuyển license sang thiết bị mới"
                }), 403
            
            # License vĩnh viễn
            if license_data.get('license_type') == 'lifetime':
                return jsonify({
                    "success": True,
                    "license_type": "lifetime",
                    "expires_at": license_data['expires_at'],
                    "activated_at": license_data['activated_at']
                }), 200
            
            # Kiểm tra thời hạn
            expires_at = datetime.fromisoformat(license_data['expires_at']).replace(tzinfo=pytz.UTC)
            if expires_at < now:
                return jsonify({
                    "success": False, 
                    "error": "License đã hết hạn",
                    "expired_date": expires_at.strftime('%d/%m/%Y')
                }), 403
                
            return jsonify({
                "success": True,
                "license_type": license_data['license_type'],
                "expires_at": license_data['expires_at'],
                "activated_at": license_data['activated_at']
            }), 200
        
        # Xử lý license mới
        if license_data.get('license_type') == 'lifetime':
            expires_at = license_data['expires_at']  # Giữ nguyên giá trị từ Firestore
        else:
            # Tính toán ngày hết hạn CHÍNH XÁC
            duration_days = license_data.get('duration_days', 0)
            if not isinstance(duration_days, int):
                duration_days = int(duration_days)
                
            expires_at = (now + timedelta(days=duration_days)).isoformat()

        # Cập nhật Firestore
        update_data = {
            'hardware_id': hardware_id,
            'activated_at': now.isoformat(),
            'expires_at': expires_at
        }
        doc_ref.update(update_data)
        
        logger.info("Kích hoạt thành công cho key: %s", key)
        
        return jsonify({
            "success": True,
            "license_type": license_data['license_type'],
            "expires_at": expires_at,
            "activated_at": now.isoformat(),
            "message": "Kích hoạt thành công"
        }), 200

    except Exception as e:
        logger.error("Lỗi kích hoạt: %s", str(e), exc_info=True)
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
