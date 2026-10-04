# sqlite-mcp-server

Server [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) sumber terbuka berbasis Python untuk menghubungkan asisten kecerdasan buatan (seperti **Claude Desktop** dan **Cursor**) ke database **SQLite lokal** dengan keamanan tingkat tinggi (*strict read-only*), proteksi batas baris (*row limit*), serta respons galat terstruktur.

[![CI](https://github.com/username/sqlite-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/username/sqlite-mcp-server/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 🌟 Fitur Utama

- **Otomatisasi Skema Database**: Alat untuk membaca daftar tabel, tipe objek (tabel/view), jumlah baris, indeks, kunci asing (*foreign keys*), dan definisi DDL secara otomatis.
- **Validasi Kueri Hanya-Baca (*Strict Read-Only*)**:
  - Pemeriksaan tingkat parser untuk menolak perintah modifikasi (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `ATTACH`, `VACUUM`, dan lain-lain).
  - Penolakan *statement chaining* (mencegah injeksi multi-pernyataan via `;`).
  - Penolakan PRAGMA berbahaya (`writable_schema`, manipulasi izin).
  - Enkapsulasi koneksi SQLite dengan mode baca-saja tingkat mesin (`file:path?mode=ro` dan `PRAGMA query_only = ON;`).
- **Proteksi Overflow Konteks (`max_rows`)**: Pemotongan baris otomatis dengan peringatan ramah AI agar kueri tabel berukuran besar tidak meluapkan *token context window* model LLM.
- **Penanganan Galat Terstruktur untuk AI**: Format galat JSON yang konsisten (`error_type`, `message`, `query`, dan `suggestion`) membantu model AI mendiagnosis dan memperbaiki kueri secara mandiri tanpa halusinasi.
- **Dukungan Penuh Protokol MCP**: Menyediakan **Tools**, **Resources** (URI skema langsung), dan **Prompts** (panduan analisis skema & asisten kueri aman).
- **Kompatibilitas Fleksibel**: Dapat dikonfigurasi melalui argumen CLI (`--db-path`), variabel lingkungan (`SQLITE_DB_PATH`), atau ditentukan secara dinamis per pemanggilan alat (`db_path`).

---

## 🛠️ Alat MCP yang Disediakan (Tools)

| Nama Alat | Deskripsi | Argumen Utama |
| :--- | :--- | :--- |
| `list_tables` | Menampilkan seluruh daftar tabel dan view beserta estimasi jumlah baris. | `db_path` *(opsional)* |
| `describe_table` | Menampilkan struktur kolom, tipe data, kunci utama, kunci asing, dan indeks suatu tabel. | `table_name` *(wajib)*, `db_path` *(opsional)* |
| `get_database_schema` | Menampilkan seluruh pernyataan `CREATE DDL` lengkap untuk semua objek database. | `db_path` *(opsional)* |
| `read_query` | Mengeksekusi kueri `SELECT` atau `EXPLAIN` yang aman dan mengembalikan baris data terstruktur. | `query` *(wajib)*, `params` *(opsional)*, `max_rows` *(opsional, default: 1000)*, `db_path` *(opsional)* |

---

## 📦 Sumber Daya & Templat Prompt MCP (Resources & Prompts)

### MCP Resources (Akses Konteks Langsung)
Klien AI yang mendukung Resource dapat membaca konteks database tanpa memanggil tool:
- `sqlite://schema`: Menampilkan seluruh DDL database terformat untuk pemahaman relasi antartabel.
- `sqlite://tables`: Menampilkan ringkasan ringkas seluruh nama tabel, view, dan jumlah baris.

### MCP Prompts (Panduan Interaktif AI)
- `schema_analysis`: Meminta model AI meninjau arsitektur database, normalisasi data, serta peluang optimasi indeks.
- `safe_query_assistant(user_goal)`: Membantu AI dan pengguna merancang kueri `SELECT` yang teroptimasi dengan klausul `LIMIT`/`OFFSET`.

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
- `ValidationError`: Parameter input (seperti nama tabel kosong atau `max_rows < 1`) tidak valid.

---

## 🚀 Panduan Instalasi & Penggunaan

### Opsi 1: Menjalankan Langsung via `uvx` (Direkomendasikan)
Jika Anda menggunakan `uv` / `uvx`, Anda dapat menjalankan server tanpa perlu mengkloning repositori:
```bash
uvx sqlite-mcp-server --db-path "C:/path/ke/database.db"
```

### Opsi 2: Instalasi Manual via Git
```bash
# 1. Kloning repositori
git clone https://github.com/username/sqlite-mcp-server.git
cd sqlite-mcp-server

# 2. Buat lingkungan virtual
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. Pasang dependensi
pip install -e ".[dev]"
```

---

## ⚙️ Konfigurasi Claude Desktop

Tambahkan konfigurasi berikut ke berkas `claude_desktop_config.json`:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### Format Konfigurasi:

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uvx",
      "args": [
        "sqlite-mcp-server",
        "--db-path",
        "C:/Users/A2/Documents/database.db"
      ]
    }
  }
}
```

*Atau menggunakan Python lokal:*
```json
{
  "mcpServers": {
    "sqlite": {
      "command": "python",
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

---

## 💻 Integrasi pada Cursor

### Metode 1: Melalui UI Pengaturan Cursor
1. Buka **Cursor Settings** (`Ctrl + Shift + J` di Windows atau `Cmd + ,` di macOS).
2. Pilih tab **Features** > **MCP Servers**.
3. Klik **+ Add New MCP Server**.
4. Masukkan parameter:
   - **Name**: `sqlite-mcp-server`
   - **Type**: `command`
   - **Command**: `python -m src.server --db-path "C:/path/to/your/database.sqlite"`

### Metode 2: Menggunakan Berkas Proyek (`.cursor/mcp.json`)
Buat berkas `.cursor/mcp.json` di direktori proyek Anda:

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

---

## 🌐 Panduan Masuk ke MCP Registry GitHub

Proyek ini telah memenuhi seluruh kriteria untuk didaftarkan ke registri ekosistem Model Context Protocol resmi ([`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers)).

### Langkah Pendaftaran:
1. **Push ke GitHub**: Unggah repositori ini ke akun GitHub publik Anda.
2. **Publikasikan ke PyPI** (opsional namun sangat disarankan):
   - Gunakan workflow terintegrasi [`.github/workflows/publish.yml`](.github/workflows/publish.yml) dengan membuat rilis baru (Release) atau tag versi `v0.1.0`.
3. **Kirim Pull Request ke `modelcontextprotocol/servers`**:
   - Fork repositori `modelcontextprotocol/servers`.
   - Tambahkan entri server ke berkas `README.md` pada kategori **Database**:
     ```markdown
     - [sqlite-mcp-server](https://github.com/username/sqlite-mcp-server) - Safe, read-only SQLite MCP server with auto schema discovery and structured AI error handling.
     ```
   - Buat Pull Request dengan judul: `Add sqlite-mcp-server to community servers`.

---

## 🧪 Pengujian Otomatis

Jalankan rangkaian pengujian unit dan integrasi dengan `pytest`:

```bash
# Jalankan seluruh tes
pytest

# Jalankan dengan laporan cakupan kode
pytest --cov=src --cov-report=term-missing
```

---

## 📂 Struktur Proyek

```
sqlite-mcp-server/
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI pengujian otomatis multi-OS (Linux & Windows)
│       └── publish.yml         # Otomatisasi rilis paket ke PyPI
├── src/
│   ├── __init__.py             # Informasi paket & versi
│   └── server.py               # Server FastMCP, alat, resources, prompts & validasi SQL
├── tests/
│   └── test_server.py          # 29 pengujian unit & integrasi pytest
├── .gitignore                  # Filter berkas Git
├── LICENSE                     # Lisensi resmi MIT
├── pyproject.toml              # Metadata proyek & konfigurasi build
├── README.md                   # Dokumentasi lengkap & panduan integrasi
└── requirements.txt            # Daftar pustaka dependensi
```

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah [Lisensi MIT](LICENSE).
