# wpa — WordPress Production Analyzer

Một file Python duy nhất. Không cần cài thêm thư viện. Chạy thẳng trên VPS.

---

## Yêu cầu bắt buộc

| | Chi tiết |
|---|---|
| **Python 3.9+** | `python3 --version` |
| **Chạy trên cùng server với WordPress** | SSH vào server trước. Tool đọc file trực tiếp, không kết nối remote. |
| **Quyền đọc WP root** | `wp-config.php`, `wp-content/`, `wp-includes/version.php` |
| **`du` + `find`** | Có sẵn trên mọi Linux — dùng cho `disk` và scan file lớn. Có Python fallback nếu thiếu. |
| **`git`** | Chỉ cần cho `git-init` |
| **Quyền ghi WP root** | Chỉ cần cho `gitignore` và `git-init` |

> Không cần: pip, virtualenv, WP-CLI, kết nối database, root.

---

## Chạy nhanh trên server mới

SSH vào server, chạy một lệnh duy nhất:

```bash
# Cài vĩnh viễn thành lệnh 'wpa' rồi chạy luôn
bash <(curl -fsSL https://raw.githubusercontent.com/YOURUSER/YOURREPO/main/install.sh) && wpa /var/www/html
```

Hoặc nếu không cần cài, **chạy thẳng không cần install**:

```bash
curl -fsSL https://raw.githubusercontent.com/YOURUSER/YOURREPO/main/wp-source.py -o /tmp/wpa.py \
  && python3 /tmp/wpa.py /var/www/html
```

> Thay `YOURUSER/YOURREPO` bằng đường dẫn repo GitHub/GitLab thực của bạn.  
> Xem mục **[Hosting script](#hosting-script)** bên dưới để biết cách push lên.

---

## Cài đặt thủ công

```bash
# Copy lên VPS
scp wp-source.py user@yourserver:~/

# SSH vào server
ssh user@yourserver

# Cài thành lệnh 'wpa'
sudo python3 ~/wp-source.py install

# Kiểm tra
wpa --help
```

Không có sudo thì chạy trực tiếp:
```bash
python3 ~/wp-source.py /var/www/html
```

---

## Hosting script

Script cần được host ở nơi có raw URL để dùng lệnh `curl` trên server.

### Cách 1: GitHub (khuyến nghị)

```bash
# Trên máy local
git init
git add wp-source.py install.sh
git commit -m "init: wpa tool"
git remote add origin git@github.com:YOURUSER/wpa.git
git push -u origin main
```

Raw URL sẽ là:
```
https://raw.githubusercontent.com/YOURUSER/wpa/main/wp-source.py
https://raw.githubusercontent.com/YOURUSER/wpa/main/install.sh
```

Sửa URL trong `install.sh`:
```bash
RAW_URL="https://raw.githubusercontent.com/YOURUSER/wpa/main/wp-source.py"
```

### Cách 2: GitLab

Raw URL format:
```
https://gitlab.com/YOURUSER/wpa/-/raw/main/wp-source.py
```

### Cách 3: Self-hosted (không dùng GitHub)

Nếu VPS có thể truy cập máy khác qua HTTP, hoặc đặt lên S3/R2/CDN:

```bash
# Đặt file lên web server bất kỳ, ví dụ Nginx
cp wp-source.py /var/www/html/tools/wpa.py

# Rồi trên server đích
curl -fsSL https://yourdomain.com/tools/wpa.py -o /tmp/wpa.py \
  && python3 /tmp/wpa.py /var/www/html
```

---

## Sử dụng chính: `wpa <path>`

Chạy một lần, tool sẽ hướng dẫn toàn bộ 5 bước:

```bash
wpa /var/www/html
```

### Flow tương tác (5 bước)

```
[1/5] WordPress Analysis
  Version: 6.5.3
  DB_NAME: prod_db  DB_USER: wp_user  DB_HOST: localhost
  Themes (2): mytheme, twentytwenty
  Plugins (8): woocommerce, contact-form-7, my-plugin ...
  uploads/ size: 2.3G

[2/5] Scanning for large items (>50MB) not covered by default .gitignore
  Default .gitignore already covers: uploads/, cache/, wp-admin/, wp-includes/, ...
  Scanning items that WILL be tracked in git:
    Scanning plugins... done
    Scanning themes... done

  Found 2 item(s) to review:

    120.0 MB  wp-content/plugins/gravity-forms
              (plugin tracked in git)
    Add to .gitignore? [y/N]: y
    -> Will be ignored.

     85.0 MB  wp-content/plugins/wpml
              (plugin tracked in git)
    Add to .gitignore? [y/N]: n
    -> Will be tracked in git.

    2.0 MB  wp-content/plugins/woocommerce/old-export.sql
            (binary file .sql — should not be in git)
    Add to .gitignore? [y/N]: y
    -> Will be ignored.

[3/5] Generating .gitignore
  Generated: /var/www/html/.gitignore
  TRACKED: themes/, plugins/, mu-plugins/, wp-config-sample.php
  IGNORED: WP core, wp-config.php, uploads/, cache/, logs, ...
  Extra (user-confirmed): gravity-forms, old-export.sql

[4/5] Git Remote
  Enter your git remote URL.
  Examples:
    git@gitlab.com:youruser/yoursite.git
    git@github.com:youruser/yoursite.git

  Remote URL (leave blank to skip push for now): git@gitlab.com:mycompany/mysite.git

[5/5] SSH Deploy Key

  Public key (/root/.ssh/id_ed25519.pub):
  ----------------------------------------------------------
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... deploy@myserver
  ----------------------------------------------------------

  Add this key to your Git server:

    GitLab > Project > Settings > Repository > Deploy keys
    Title       : deploy@myserver
    Key         : (paste the key above)
    Write access: NO  (read-only is enough for clone/pull)

  Press Enter when you've added the deploy key...
  Testing connection to gitlab.com... OK
  Welcome to GitLab, @mycompany!

  Initialized git repo.
  Generated: /var/www/html/.gitignore
  Created initial commit.
  Pushed to git@gitlab.com:mycompany/mysite.git  (branch: main)

  Clone on local:
    git clone git@gitlab.com:mycompany/mysite.git

  Setup complete!

  Local dev next steps:
    wpa local-setup /var/www/html
```

---

## Logic bước 2: Scan file lớn

**Đã được ignore sẵn** (tool không hỏi về những thứ này):
- `uploads/`, `cache/`, `backup-db/`, `upgrade/`, `wflogs/`
- `wp-admin/`, `wp-includes/`
- `wp-config.php`

**Tool hỏi về** (>50MB và sẽ vào git nếu không ignore):
- Từng plugin trong `wp-content/plugins/` nếu > 50MB
- Từng theme trong `wp-content/themes/` nếu > 50MB
- Các subdirectory khác trong `wp-content/` nếu > 50MB

**Tool hỏi về bất kể size** (luôn nguy hiểm khi vào git):
- File `.sql`, `.zip`, `.tar.gz`, `.bak`, `.rar`, `.dump`, `.mp4`, `.psd` ... > 1MB nằm ngoài `uploads/`

---

## Các lệnh riêng lẻ

```bash
wpa info        /var/www/html                          # Thông tin WP
wpa disk        /var/www/html                          # Phân tích dung lượng
wpa gitignore   /var/www/html                          # Tạo .gitignore
wpa git-init    /var/www/html git@gitlab.com:u/r.git   # Init git + push
wpa local-setup /var/www/html                          # Hướng dẫn setup local
wpa deploy-key                                         # Xem SSH public key
wpa install                                            # Cài thành lệnh 'wpa'
```

### `wpa deploy-key` — Lấy SSH public key

```bash
wpa deploy-key
```

- Tìm key tại `~/.ssh/id_ed25519.pub`, `~/.ssh/id_rsa.pub`, `~/.ssh/id_ecdsa.pub`
- Nếu không có, **tự generate** key ed25519 mới
- In key ra màn hình kèm hướng dẫn thêm vào GitLab/GitHub/Bitbucket

### `wpa disk` — Phân tích dung lượng

```
  Directory sizes:
    2.3 GB  wp-content/uploads/   [gitignored]
  450.0 MB  wp-content/plugins/   [tracked in git]
   80.0 MB  wp-content/themes/    [tracked in git]
   35.0 MB  wp-content/cache/     [gitignored]

  File types in uploads/:
    1.1 GB  images  (jpg/png/gif/webp...)
  800.0 MB  video   (mp4/avi/mov...)
  320.0 MB  docs    (pdf/doc/xls...)

  Plugins by size (top 10):
  120.0 MB  gravity-forms/
   45.0 MB  wpml/

  Suspicious files outside uploads/ (>5MB):
   45.0 MB  wp-content/plugins/old-plugin/data.sql  <-- add to .gitignore!

  Estimated git repo size (themes + plugins):
    ~530 MB
```

---

## Sau khi push lên git

```bash
# Clone về local
git clone git@gitlab.com:youruser/yoursite.git mysite
cd mysite

# Xem hướng dẫn chi tiết
wpa local-setup /var/www/html
```

Gồm 5 bước: download WP core cùng version → tạo wp-config.php → import DB → search-replace URL → copy uploads.

---

## Test

```bash
python3 test_local.py
```

---

## Cách hoạt động

Tool đọc file trực tiếp. **Không kết nối database. Không gọi WP API.**

| Thông tin | Nguồn |
|---|---|
| WP version | `wp-includes/version.php` |
| DB config | `wp-config.php` — regex `define('DB_*', ...)` |
| DB password | Luôn mask `***hidden***`, không bao giờ hiển thị |
| Themes | `wp-content/themes/*/style.css` — parse CSS header |
| Plugins | `wp-content/plugins/*/` — tìm PHP file có `Plugin Name:` |
| Kích thước thư mục | `du -sb` (bytes) và `du -sh` (human) |
| File type breakdown | `find <dir> -type f -printf "%s %f\n"` |
| File lớn ngoài uploads | `find -size +NM` → fallback `os.walk` nếu `find` không có |
| SSH key | `~/.ssh/id_ed25519.pub` → `id_rsa.pub` → tự generate nếu cần |

---

## Giới hạn

| Giới hạn | Lý do |
|---|---|
| **Không biết plugin/theme nào đang active** | Active status trong DB (`wp_options`). Tool liệt kê tất cả đã cài. |
| **Không tự phân biệt stock vs custom** | Phải review danh sách comment trong `.gitignore` thủ công. |
| **Không dump DB, không copy uploads** | Nằm ngoài scope — tool chỉ phân tích source và setup git. |
| **`disk` chậm nếu uploads có >50k files** | `find -printf` phải duyệt toàn bộ. Mất 30-60 giây. |
| **Không hỗ trợ Bedrock / custom WP structure** | Cần `wp-config.php` ở root. |
| **`wp-config.php` dùng `getenv()` thay hardcode** | DB info sẽ trống. Tool không chạy PHP. |
| **Không chạy remote** | Phải SSH vào server trước. |
