import pg8000.dbapi
import ssl

def get_connection():
    context = ssl.create_default_context()
    
    # تم وضع البيانات الدقيقة جداً لحل مشكلة المصادقة
    conn = pg8000.dbapi.connect(
        host="ep-fragrant-water-alyos8cz-pooler.c-3.eu-central-1.aws.neon.tech",
        database="neondb",
        user="neondb_owner",
        password="npg_cXHMGpT80QUt", # السر كان في الرقم صفر 0 هنا!
        port=5432,
        ssl_context=context
    )
    return conn