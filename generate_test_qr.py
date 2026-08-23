import requests
import qrcode
import sys

# Cấu hình API và Link gốc
API_URL = "http://localhost:8000/api/qr/generate"
TARGET_URL = "https://colora.vn/san-pham/day-chuyen-demo"
OUTPUT_FILE = "colora_test_qr.png"

def main():
    print(f"🚀 [1/3] Đang gửi yêu cầu mã hóa link: {TARGET_URL}...")
    
    try:
        # Gọi API (Đảm bảo FastAPI backend đang chạy ở cổng 8000)
        response = requests.post(API_URL, json={"target_url": TARGET_URL})
        response.raise_for_status()
        
        # Bóc tách chuỗi định tuyến kép từ API (Layer 1 + Layer 2)
        # Lưu ý: Sửa key "secure_url" nếu schema Pydantic trong FastAPI của bạn trả về tên khác
        data = response.json()
        secure_qr_string = data.get("secure_url") or data.get("qr_url")
        
        if not secure_qr_string:
            print("❌ Lỗi: Backend không trả về dữ liệu chuỗi QR.")
            sys.exit(1)
            
        print("✅ [2/3] Bọc 8 lớp bảo mật thành công!")
        print(f"🔗 Chuỗi QR (xem trước): {secure_qr_string[:60]}...")
        
        # Render hình ảnh mã QR (Mức độ sửa lỗi H - Cao nhất)
        print(f"🎨 [3/3] Đang kết xuất ra ảnh '{OUTPUT_FILE}'...")
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(secure_qr_string)
        qr.make(fit=True)

        # Trích xuất ảnh cơ bản
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(OUTPUT_FILE)
        
        print(f"🎉 HOÀN TẤT! Hãy mở file '{OUTPUT_FILE}' trên màn hình và dùng điện thoại quét thử.")
        
    except requests.exceptions.ConnectionError:
        print("❌ Lỗi kết nối: Không thể gọi đến API. Vui lòng đảm bảo FastAPI đang chạy ở localhost:8000.")
    except Exception as e:
        print(f"❌ Đã xảy ra lỗi: {e}")

if __name__ == "__main__":
    main()
