# United Paints ERP — Live Dashboard
## UC & UP Invoice Intelligence System

---

## DEFAULT LOGIN CREDENTIALS

| Who            | Username              | Password    |
|----------------|-----------------------|-------------|
| Muruga (Admin) | `muruga`              | `Admin@2026` |
| Akshai Sir     | `akshai_sir`          | `Mgmt@2026`  |
| Aakhash Sir    | `aakhash_sir`         | `Mgmt@2026`  |
| Ashok Sir      | `ashok_sir`           | `Mgmt@2026`  |
| Vijay          | `vijay`               | `Rep@2026`   |
| U. Kannan      | `u_kannan`            | `Rep@2026`   |
| L. Sreenivasan | `l_sreenivasan`       | `Rep@2026`   |
| L.S. Covai     | `l_sreenivasan_covai` | `Rep@2026`   |
| Babu           | `babu`                | `Rep@2026`   |
| T. Dhinakaran  | `t_dhinakaran`        | `Rep@2026`   |
| Deepak         | `deepak`              | `Rep@2026`   |

> **Important:** Ask everyone to change their passwords after first login!

---

## DAILY WORKFLOW (every morning, 2 minutes)

1. Download invoice PDFs from Google Drive
2. Open: `https://your-domain.com/upload-page`
3. Select company (UC or UP)
4. Drag and drop PDFs
5. Click "Upload & Process"
6. Done! Dashboard updates for everyone.

---

## FOLDER STRUCTURE

```
erp_live/
├── main.py                  ← App entry point
├── database.py              ← DB connection
├── models.py                ← Database tables
├── auth.py                  ← Login & security
├── requirements.txt         ← Python libraries
├── railway.json             ← Deploy config
├── migrate_from_html.py     ← ONE-TIME: load existing data
├── routers/
│   ├── auth_router.py       ← Login API
│   ├── data_router.py       ← Dashboard data API
│   └── upload_router.py     ← PDF upload API
├── extractor/
│   └── pdf_extractor.py     ← PDF reading logic
└── static/
    ├── login.html           ← Login page
    ├── upload.html          ← Daily upload page
    └── Erp_Final.html       ← Your dashboard (copy here!)
```

---

## API ENDPOINTS

| Endpoint | What it does |
|----------|-------------|
| `GET /` | Login page |
| `GET /dashboard` | ERP Dashboard |
| `GET /upload-page` | Upload PDFs (admin only) |
| `POST /api/auth/login` | Login |
| `GET /api/data/summary` | KPI summary |
| `GET /api/data/bills` | Invoice list |
| `GET /api/data/rep-performance` | Rep rankings |
| `GET /api/data/products` | Product movement |
| `POST /api/upload/pdf` | Upload one PDF |
| `POST /api/upload/bulk-pdfs` | Upload multiple PDFs |
| `GET /api/docs` | Full API documentation |
