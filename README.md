# sqlite-mcp-server

Server [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) sumber terbuka berbasis Python untuk menghubungkan asisten kecerdasan buatan (seperti **Claude Desktop** dan **Cursor**) ke database **SQLite lokal** dengan keamanan tingkat tinggi (strict read-only) dan respons galat terstruktur.

---

## 🌟 Fitur Utama

- **Otomatisasi Skema Database**: Alat untuk membaca daftar tabel, tipe objek (tabel/view), jumlah baris, indeks, kunci asing (foreign keys), dan definisi DDL secara otomatis.
- **Validasi Kueri Hanya-Baca (Strict Read-Only)**:
  - Pemeriksaan tingkat parser untuk menolak perintah modifikasi (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `VACUUM`, dan lain-lain).
  - Penolakan *statement chaining* (mencegah eksekusi multi-pernyataan via `;`).
  - Penolakan PRAGMA berbahaya (`writable_schema`, manipulasi izin).
  - Enkapsulasi koneksi SQLite dengan mode baca-saja tingkat mesin (`file:path?mode=ro` dan `PRAGMA query_only = ON`).
- **Penanganan Galat Terstruktur untuk AI**: Format galat JSON yang konsisten (`error_type`, `message`, `query`, dan `suggestion`) membantu model AI mendiagnosis dan memperbaiki kueri secara mandiri tanpa halusinasi.
- **Kompatibilitas Fleksibel**: Dapat dikonfigurasi melalui argumen CLI (`--db-path`), variabel lingkungan (`SQLITE_DB_PATH`), atau ditentukan secara dinamis per pemanggilan alat (`db_path`).

---

## 🛠️ Alat MCP yang Disediakan

| Nama Alat | Deskripsi | Argumen Utama |
| :--- | :--- | :--- |
| `list_tables` | Menampilkan seluruh daftar tabel dan view beserta estimasi jumlah baris. | `db_path` *(opsional)* |
| `describe_table` | Menampilkan struktur kolom, tipe data, kunci utama, kunci asing, dan indeks suatu tabel. | `table_name` *(wajib)*, `db_path` *(opsional)* |
| `get_database_schema` | Menampilkan seluruh pernyataan `CREATE DDL` lengkap untuk semua objek database. | `db_path` *(opsional)* |
| `read_query` | Mengeksekusi kueri `SELECT` atau `EXPLAIN` yang aman dan mengembalikan baris data terstruktur. | `query` *(wajib)*, `params` *(opsional)*, `db_path` *(opsional)* |

---

## 📋 Struktur Galat Terstruktur (Structured Error Handling)

Ketika terjadi kesalahan sintaks atau kueri yang dilarang, server mengembalikan format JSON yang ramah AI:

```json
{
  "success": false,
  "error_type": "DisallowedQueryError",
  "message": "Forbidden modification keyword 'DROP' detected. Only read operations are allowed.",
  "query": "DROP TABLE employees;",
  "suggestion": "Remove any data modification or schema alteration commands. Only SELECT queries are permitted."
}
```

Tipe galat yang didukung:
- `DisallowedQueryError`: Kueri mencoba memodifikasi database atau menggunakan kata kunci terlarang.
- `SyntaxError`: Galat sintaks SQL dari SQLite.
- `TableNotFoundError`: Tabel yang diminta tidak ditemukan di database (dilengkapi saran memeriksa via `list_tables`).
- `ColumnNotFoundError`: Kolom yang diminta tidak ada (dilengkapi saran memeriksa via `describe_table`).
- `DatabaseNotFoundError`: Berkas SQLite tidak ditemukan pada jalur yang diberikan.
- `DatabaseConfigError`: Jalur database belum ditentukan di argumen atau variabel lingkungan.

---

## 🚀 Panduan Instalasi

### Prasyarat
- Python 3.10 atau versi yang lebih baru
- `pip` dan `virtualenv`

### 1. Kloning Repositori
```bash
git clone https://github.com/username/sqlite-mcp-server.git
cd sqlite-mcp-server
```

### 2. Buat Lingkungan Virtual (Virtual Environment)
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Pasang Dependensi
```bash
pip install -e .
# Atau pasang dependensi pengembangan (pengujian)
pip install -e ".[dev]"
```

---

## ⚙️ Konfigurasi Claude Desktop

Untuk mengintegrasikan server ini ke aplikasi **Claude Desktop**, tambahkan konfigurasi ke berkas `claude_desktop_config.json`.

### Lokasi Berkas Konfigurasi:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
  *(contoh: `C:\Users\<NamaPengguna>\AppData\Roaming\Claude\claude_desktop_config.json`)*
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Contoh Konfigurasi:

#### Opsi A: Menggunakan Python dari Virtual Environment (Direkomendasikan)
```json
{
  "mcpServers": {
    "local-sqlite": {
      "command": "C:/Users/A2/Downloads/sqlite-mcp-server/.venv/Scripts/python.exe",
      "args": [
        "-m",
        "src.server",
        "--db-path",
        "C:/Users/A2/Documents/database.db"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

*(Catatan macOS/Linux: Ganti jalur `command` menjadi `/path/to/sqlite-mcp-server/.venv/bin/python`)*

#### Opsi B: Menggunakan Paket yang Terpasang di Sistem via `sqlite-mcp-server`
```json
{
  "mcpServers": {
    "local-sqlite": {
      "command": "sqlite-mcp-server",
      "args": [
        "--db-path",
        "/absolute/path/to/your/database.sqlite"
      ]
    }
  }
}
```

---

## 💻 Integrasi pada Cursor

Cursor mendukung MCP Server secara bawaan untuk asisten Composer dan Chat.

### Metode 1: Melalui Pengaturan Cursor (UI)
1. Buka **Cursor Settings** (`Ctrl + Shift + J` di Windows/Linux atau `Cmd + ,` di macOS).
2. Masuk ke menu **Features** > **MCP Servers**.
3. Klik tombol **+ Add New MCP Server**.
4. Isi data sebagai berikut:
   - **Name**: `sqlite-mcp-server`
   - **Type**: `command`
   - **Command**: `python -m src.server --db-path "C:/path/to/your/database.sqlite"`
     *(Atau gunakan jalur penuh ke `python.exe` dalam `.venv`)*

### Metode 2: Menggunakan Berkas Konfigurasi Proyek (`.cursor/mcp.json`)
Buat berkas `.cursor/mcp.json` di dalam repositori atau proyek kerja Anda:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "python",
      "args": [
        "-m",
        "src.server",
        "--db-path",
        "${workspaceFolder}/data/app.db"
      ]
    }
  }
}
```

Setelah konfigurasi disimpan, restart Cursor atau refresh daftar MCP di panel Cursor. Cursor akan secara otomatis mengenali alat `list_tables`, `describe_table`, `get_database_schema`, dan `read_query`.

---

## 🧪 Pengujian Otomatis

Proyek ini telah dilengkapi dengan rangkaian pengujian komprehensif menggunakan `pytest`.

Jalankan pengujian:
```bash
pytest
```

Jalankan pengujian beserta laporan cakupan kode (coverage):
```bash
pytest --cov=src --cov-report=term-missing
```

---

## 📂 Struktur Proyek

```
sqlite-mcp-server/
├── .github/
│   └── workflows/
│       └── ci.yml              # Pipeline otomatisasi CI GitHub Actions
├── src/
│   ├── __init__.py             # Informasi paket & versi
│   └── server.py               # Inisialisasi FastMCP, validasi kueri & perkakas
├── tests/
│   └── test_server.py          # Pengujian unit & integrasi pytest
├── .gitignore                  # Berkas yang diabaikan oleh Git
├── LICENSE                     # Lisensi resmi MIT
├── pyproject.toml              # Definisi metadata proyek & dependensi
├── README.md                   # Dokumentasi lengkap & panduan penggunaan
└── requirements.txt            # Daftar pustaka dependensi Python
```

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE). Bebas digunakan, dimodifikasi, dan didistribusikan untuk keperluan komersial maupun non-komersial.
