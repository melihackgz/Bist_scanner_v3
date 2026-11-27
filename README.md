# BIST Nicel Karar Destek ve Tarama Platformu

Eğitim ve karar destek amaçlı Borsa İstanbul teknik, bilanço ve risk yönetimi tarayıcısı.

## Kurulum ve Çalıştırma
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Birim Testleri
```bash
pytest -v
```

## Arka Plan Tarayıcısı (Cron / GitHub Actions)
```bash
python -m jobs.scheduled_scan
```

## Bulut Dağıtımı & Kalıcı Depolama Notu
Streamlit Community Cloud gibi ortamlarda yerel disk geçicidir (`journal.db` yeniden başlatmalarda sıfırlanabilir). Kalıcı işlem günlüğü için `storage/repository.py` katmanını **Supabase (PostgreSQL)** veya **Turso (libSQL)** bağlantısına yönlendirmeniz önerilir.
