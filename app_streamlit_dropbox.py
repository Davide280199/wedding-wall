import os, io, json, secrets, time
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image
import qrcode
import dropbox

APP_KEY = st.secrets["vcf89yjvlnew3zu"]
APP_SECRET = st.secrets["jgxe5so0lotuqd8"]
REFRESH_TOKEN = st.secrets["ehHRexbEWocAAAAAAAAAAcUU2WX7tg_MRvs8rkMDKpUwQVeWVqiMKkT_a_Ins17-"]

dbx = dropbox.Dropbox(
    oauth2_refresh_token=REFRESH_TOKEN,
    app_key=APP_KEY,
    app_secret=APP_SECRET,
)

# test chiaro in app
try:
    acct = dbx.users_get_current_account()
    st.caption(f"Connesso a Dropbox come: {acct.name.display_name}")
except dropbox.exceptions.AuthError:
    st.error("Autenticazione Dropbox fallita. Ricontrolla KEY/SECRET/REFRESH_TOKEN e i permessi (read/write/metadata).")
    st.stop()
# ============ Config ============
TITLE = st.secrets.get("APP_TITLE", "Wedding Wall")
DEFAULT_EVENT_CODE = st.secrets.get("DEFAULT_EVENT_CODE", "CristianoLorena")
DROPBOX_TOKEN = st.secrets["DROPBOX_TOKEN"]  # deve esistere nei Secrets!

EVENT_CODE = st.experimental_get_query_params().get("code", [DEFAULT_EVENT_CODE])[0]
APP_FOLDER = f"/wedding/{EVENT_CODE}"           # su Dropbox
INDEX_PATH = f"{APP_FOLDER}/index.json"         # metadati (likes, nickname, msg)

st.set_page_config(page_title=TITLE, page_icon="💍", layout="wide")

# ============ Dropbox client ============
dbx = dropbox.Dropbox(DROPBOX_TOKEN)

def dbx_ensure_folder(path: str):
    try:
        dbx.files_get_metadata(path)
    except dropbox.exceptions.ApiError:
        dbx.files_create_folder_v2(path, autorename=False)

def dbx_download(path: str) -> bytes | None:
    try:
        md, resp = dbx.files_download(path)
        return resp.content
    except dropbox.exceptions.ApiError:
        return None

def dbx_upload(path: str, data: bytes, rev: str | None = None):
    mode = dropbox.files.WriteMode.overwrite if not rev else dropbox.files.WriteMode.update(rev)
    return dbx.files_upload(data, path, mode=mode, mute=True)

def dbx_temp_link(path: str) -> str:
    # URL temporaneo (scade ~4h), perfetto per la galleria
    return dbx.files_get_temporary_link(path).link

# ============ Style / Theme ============
st.markdown("""
<style>
:root { --blush:#ffd6e0; --accent:#ff7aa2; --bg:#0f0f11; --card:#161618; --muted:#d9d1cc; }
#root, .main { background: radial-gradient(1200px 600px at 50% -200px, rgba(255,214,224,.12), transparent 60%), var(--bg) !important; }
.block-container { padding-top: 1.2rem; }
body::after{
  content:"Cristiano  &  Lorena";
  position:fixed; inset:0; text-align:center;
  font-weight:800; font-size:12vw; line-height:100vh;
  color:rgba(255,214,224,0.05); pointer-events:none; user-select:none;
}
.card{ background:var(--card); border:1px solid rgba(255,255,255,.06); border-radius:18px; padding:14px; }
.meta{ color:var(--muted); font-size:12px; display:flex; justify-content:space-between; margin:.3rem 0 .2rem; }
.nick{ color:var(--blush); font-weight:700; }
.likebtn{ display:inline-block; background:linear-gradient(135deg, var(--blush), var(--accent));
  color:#311117; padding:.45rem .75rem; border-radius:12px; font-weight:900; border:none; }
.caption{ margin:.25rem 0 .4rem; }
</style>
""", unsafe_allow_html=True)

# ============ Utils ============
def slugify_name(name: str) -> str:
    if not name: return "guest"
    keep = [c for c in name.lower() if c.isalnum() or c in ["-","_"]]
    s = "".join(keep).strip("-_")
    return s or "guest"

def process_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode in ("RGBA","P","LA"):
        bg = Image.new("RGB", img.size, (255,255,255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    # resize max 1920
    w,h = img.size
    scale = min(1.0, 1920/max(w,h))
    if scale < 1.0:
        img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    return img

def load_index() -> tuple[list[dict], str | None]:
    """Ritorna (items, rev). items = lista immagini ordinate desc per ts"""
    metadata = None
    content = dbx_download(INDEX_PATH)
    if content is None:
        return [], None
    # recupera la revisione per update atomico
    try:
        metadata = dbx.files_get_metadata(INDEX_PATH)
    except Exception:
        metadata = None
    items = json.loads(content.decode("utf-8"))
    items.sort(key=lambda x: x.get("ts",""), reverse=True)
    rev = getattr(metadata, "rev", None)
    return items, rev

def save_index(items: list[dict], rev: str | None):
    data = json.dumps(items, ensure_ascii=False).encode("utf-8")
    try:
        dbx_upload(INDEX_PATH, data, rev=rev)
    except dropbox.exceptions.ApiError:
        # conflitto: ricarica e riprova una volta
        current, current_rev = load_index()
        # merge naive: mantieni la lista più lunga
        if len(current) > len(items):
            items = current
        dbx_upload(INDEX_PATH, json.dumps(items).encode("utf-8"), rev=current_rev)

def ensure_index():
    dbx_ensure_folder(APP_FOLDER)
    if dbx_download(INDEX_PATH) is None:
        save_index([], None)

def add_records(new_items: list[dict]):
    items, rev = load_index()
    # evita duplicati per id
    existing_ids = {x["id"] for x in items}
    for it in new_items:
        if it["id"] not in existing_ids:
            items.append(it)
    save_index(items, rev)

def increment_like(img_id: str):
    items, rev = load_index()
    for it in items:
        if it["id"] == img_id:
            it["likes"] = int(it.get("likes",0)) + 1
            break
    save_index(items, rev)

# ============ Init ============
ensure_index()

# ============ Header / Tabs ============
st.markdown(f"### 💍 Cristiano & Lorena — *{EVENT_CODE}*")
tab_upload, tab_gallery, tab_qr = st.tabs(["📤 Upload", "🖼️ Gallery", "🔗 QR"])

# ============ Upload ============
with tab_upload:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Carica le tue foto")
    st.caption("Scegli 1 o più immagini. Ridimensioniamo automaticamente per velocizzare. Formati: JPG/PNG.")

    c1, c2 = st.columns(2)
    nickname = c1.text_input("Nickname (opzionale)", placeholder="es. ziaPina")
    message  = c2.text_input("Messaggio (opzionale)", placeholder="Auguri agli sposi!")
    files = st.file_uploader("Foto", type=["jpg","jpeg","png"], accept_multiple_files=True, label_visibility="collapsed")

    if files:
        st.caption(f"Selezionate: {len(files)} foto")

    if st.button("Carica", type="primary"):
        if not files:
            st.warning("Nessun file selezionato.")
        else:
            safe_nick = slugify_name(nickname)
            now = datetime.utcnow()
            new_items = []
            for f in files:
                # process
                img = process_image(f.read())
                base = os.path.splitext(os.path.basename(f.name))[0]
                ts = now.isoformat()
                safe_name = f"{safe_nick}_{now.strftime('%Y%m%d-%H%M%S')}_{base}.jpg"
                # salva su Dropbox
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85, optimize=True)
                buf.seek(0)
                dbx_upload(f"{APP_FOLDER}/{safe_name}", buf.read())
                # record
                rec = {
                    "id": secrets.token_hex(8),
                    "path": f"{APP_FOLDER}/{safe_name}",
                    "filename": safe_name,
                    "nickname": safe_nick or "guest",
                    "message": message or "",
                    "ts": ts,
                    "likes": 0,
                }
                new_items.append(rec)
                time.sleep(0.05)
            add_records(new_items)
            st.success(f"✅ Caricate {len(new_items)} foto!")
            st.experimental_rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ============ Gallery ============
with tab_gallery:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("Galleria Live 🎉")
    st.caption("Si aggiorna ogni 10s. Tocca ❤ per mettere like.")
    st.markdown('</div>', unsafe_allow_html=True)

    # leggero auto-refresh (quando l’utente interagisce)
    st.experimental_set_query_params(code=EVENT_CODE, _=secrets.token_hex(2))
    items, _ = load_index()

    if not items:
        st.info("Ancora nessuna foto. Caricane una dalla tab *Upload*!")
    else:
        # 2 colonne su mobile, 3+ su desktop
        cols = st.columns(2) if st.runtime.scriptrunner.script_run_context is None else st.columns(3)
        for i, it in enumerate(items):
            with cols[i % len(cols)]:
                try:
                    link = dbx_temp_link(it["path"])
                    st.image(link, use_column_width=True)
                except Exception:
                    st.warning("Immagine non disponibile (link temporaneo scaduto). Ricarica la pagina.")
                    continue
                st.markdown(f"""<div class="meta"><span class="nick">{it['nickname']}</span>
                                <span>{it['ts'][:16].replace('T',' ')}</span></div>""", unsafe_allow_html=True)
                if it.get("message"):
                    st.markdown(f"<div class='caption'>{it['message']}</div>", unsafe_allow_html=True)
                c1, c2 = st.columns([1,1.2])
                liked_key = f"liked_{it['id']}"
                with c1:
                    if st.button(f"❤ {it.get('likes',0)}", key=f"like_{it['id']}", use_container_width=True):
                        if not st.session_state.get(liked_key, False):
                            increment_like(it["id"])
                            st.session_state[liked_key] = True
                            st.experimental_rerun()
                with c2:
                    st.link_button("Apri", link, use_container_width=True)

# ============ QR ============
with tab_qr:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("QR da stampare")
    # base URL dell'app Streamlit (pubblico)
    base = st.text_input("Base URL pubblico", value=st.request.url_root.rstrip("/"))
    app_url = f"{base}/?code={EVENT_CODE}"

    st.write("**Link unico (Upload + Gallery):**")
    st.code(app_url, language="text")

    def make_qr(url: str) -> bytes:
        img = qrcode.make(url)
        b = io.BytesIO()
        img.save(b, format="PNG")
        return b.getvalue()

    st.image(make_qr(app_url), caption="Inquadra per entrare", width=220)
    st.download_button("Scarica QR (PNG)", data=make_qr(app_url), file_name="wedding-qr.png", mime="image/png")
    st.markdown('</div>', unsafe_allow_html=True)
