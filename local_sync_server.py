from http.server import HTTPServer, BaseHTTPRequestHandler
import subprocess
import datetime
import json
import re
import os

MONTHS = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC']
MAPPING_FILE = os.path.join(os.path.dirname(__file__), "monthly_sheets.json")
HTML_FILE = os.path.join(os.path.dirname(__file__), "index.html")

def get_current_month_title():
    now = datetime.datetime.now()
    return f"{MONTHS[now.month - 1]}-{now.year}"

def run_cmd(args):
    cmd = ["gsheets"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.returncode == 0, result.stdout, result.stderr

def load_sheet_mapping():
    if os.path.exists(MAPPING_FILE):
        try:
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "OCT-2026": "1V4iSAhAh7xM_1RWtODSNZ-Nix5ji7fF-CIKWlei3Ev0",
        "NOV-2026": "1s88JU2SGM3Rtg0uDZNgbDpqFCtgFxWcXdr-1TzeOeeE"
    }

def save_sheet_mapping(mapping):
    try:
        with open(MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("Error guardando mapa de hojas:", e)

def get_or_create_monthly_sheet(month_title=None):
    if not month_title:
        month_title = get_current_month_title()

    mapping = load_sheet_mapping()
    if month_title in mapping:
        return mapping[month_title]

    print(f"\n[AUTO-MES] No se encontró hoja para '{month_title}'. Verificando en Google Drive...")
    ok, out, _ = run_cmd(["readonly", "list", month_title])
    if ok and month_title in out:
        match = re.search(r"(\b[a-zA-Z0-9_-]{35,}\b)", out)
        if match:
            found_id = match.group(1)
            print(f" -> Encontrada hoja existente '{month_title}': {found_id}")
            mapping[month_title] = found_id
            save_sheet_mapping(mapping)
            return found_id

    print(f"[AUTO-MES] Creando nueva hoja mensual '{month_title}' en Google Drive...")
    ok, out, err = run_cmd(["mutate", "create", month_title, "--json"])
    if not ok:
        print(f"Error creando hoja mensual: {err}")
        return mapping.get("NOV-2026", "1s88JU2SGM3Rtg0uDZNgbDpqFCtgFxWcXdr-1TzeOeeE")

    match = re.search(r"ID:\s*([a-zA-Z0-9_-]+)", out)
    if not match:
        match = re.search(r"\"spreadsheetId\":\s*\"([^\"]+)\"", out)
    
    if match:
        new_id = match.group(1)
        print(f" -> Creada exitosamente hoja '{month_title}': {new_id}")

        run_cmd(["mutate", "rename-sheet", new_id, "--sheet-id", "0", "--title", "Inventario"])
        run_cmd(["mutate", "add-sheet", new_id, "--title", "Clientes"])
        run_cmd(["mutate", "format", new_id, "--sheet-id", "0", "--start-row", "0", "--end-row", "1", "--start-col", "0", "--end-col", "8", "--bold", "--align", "CENTER", "--bg-color", "#059669", "--fg-color", "#FFFFFF"])
        run_cmd(["mutate", "freeze", new_id, "--sheet-id", "0", "--rows", "1"])

        mapping[month_title] = new_id
        save_sheet_mapping(mapping)
        return new_id

    return mapping.get("NOV-2026", "1s88JU2SGM3Rtg0uDZNgbDpqFCtgFxWcXdr-1TzeOeeE")

class SyncHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        landing_file = os.path.join(os.path.dirname(__file__), "landing.html")
        if self.path in ['/landing', '/landing.html']:
            if os.path.exists(landing_file):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(landing_file, 'rb') as f:
                    self.wfile.write(f.read())
                return

        # Si entra a la raíz o a index.html, servir la aplicación POS completa
        if self.path in ['/', '/index.html', '/app', '/pos']:
            if os.path.exists(HTML_FILE):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(HTML_FILE, 'rb') as f:
                    self.wfile.write(f.read())
                return

        # Si entra a /api/import o /import, leer directamente la tabla de Google Sheets
        if self.path in ['/api/import', '/import', '/api/inventario']:
            month_title = get_current_month_title()
            sheet_id = get_or_create_monthly_sheet(month_title)
            print(f"\n[IMPORT] Leyendo inventario desde Google Sheet '{month_title}' ({sheet_id})...")
            
            ok, out, err = run_cmd(["readonly", "read", sheet_id, "Inventario!A2:H100"])
            products = []
            emoji_map = {
                "Alimento": "🥣",
                "Salud": "💊",
                "Juguetes": "🪀",
                "Higiene": "🧼",
                "Accesorios": "🎀"
            }
            if ok and out.strip():
                for line in out.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 2 and parts[0].strip():
                        id_str = parts[0].strip()
                        id_val = int(id_str) if id_str.isdigit() else len(products) + 1
                        name = parts[1].strip()
                        cat = parts[2].strip() if len(parts) > 2 else "Alimento"
                        price = float(parts[3].replace(",", "").replace("$", "").strip()) if len(parts) > 3 and parts[3].strip() else 0
                        stock = int(parts[4].strip()) if len(parts) > 4 and parts[4].strip().isdigit() else 0
                        min_s = int(parts[5].strip()) if len(parts) > 5 and parts[5].strip().isdigit() else 2
                        url = parts[7].strip() if len(parts) > 7 else ""
                        products.append({
                            "id": id_val,
                            "name": name,
                            "category": cat,
                            "price": price,
                            "stock": stock,
                            "minStock": min_s,
                            "imageUrl": url,
                            "emoji": emoji_map.get(cat, "🐾")
                        })
                print(f" -> Importados exitosamente {len(products)} productos desde Google Sheets.")

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "month": month_title,
                "sheetId": sheet_id,
                "products": products
            }, ensure_ascii=False).encode('utf-8'))
            return

        # Si entra a /status o /api/status, retornar estado JSON
        month_title = get_current_month_title()
        sheet_id = get_or_create_monthly_sheet(month_title)
        mapping = load_sheet_mapping()

        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "online",
            "currentMonth": month_title,
            "activeSheetId": sheet_id,
            "history": mapping
        }).encode())

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            month_title = data.get("monthTitle") or get_current_month_title()
            sheet_id = get_or_create_monthly_sheet(month_title)

            print(f"\n[SYNC] Sincronizando con tabla mensual '{month_title}' (ID: {sheet_id})...")
            
            # 1. Sincronizar Inventario
            if "tables" in data and "inventario" in data["tables"]:
                prods = data["tables"]["inventario"]
                inv_rows = ["ID,Producto,Categoría,Precio COP,Stock Actual,Stock Mínimo,Estado Semáforo,URL"]
                for p in prods:
                    nombre = str(p.get("nombre", "")).replace(",", " ")
                    cat = str(p.get("categoria", "")).replace(",", " ")
                    url = str(p.get("url", "")).replace(",", "%2C")
                    inv_rows.append(f"{p.get('id')},{nombre},{cat},{p.get('precio')},{p.get('stock_actual')},{p.get('stock_minimo')},{p.get('estado')},{url}")
                
                inv_data = "|".join(inv_rows)
                end_row = len(inv_rows)
                run_cmd(["mutate", "write", sheet_id, f"Inventario!A1:H{end_row}", inv_data])
                print(f" -> Inventario actualizado ({len(prods)} productos con URL)")

            # 2. Sincronizar Clientes
            if "tables" in data and "clientes" in data["tables"]:
                clis = data["tables"]["clientes"]
                cli_rows = ["ID,Nombre Completo,Teléfono Contacto,Compras Realizadas,Total Gastado COP,Fecha Registro"]
                for c in clis:
                    nombre = str(c.get("nombre", "")).replace(",", " ")
                    tel = str(c.get("contacto", "")).replace(",", " ")
                    cli_rows.append(f"{c.get('id')},{nombre},'{tel},{c.get('tickets_totales')},{c.get('gasto_total')},{c.get('fecha_registro')}")
                
                cli_data = "|".join(cli_rows)
                end_row = len(cli_rows)
                run_cmd(["mutate", "write", sheet_id, f"Clientes!A1:F{end_row}", cli_data])
                print(f" -> Clientes actualizados ({len(clis)} clientes)")

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "month": month_title,
                "sheetId": sheet_id
            }).encode())
        except Exception as e:
            print("Error en sincronización:", e)
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

def run_server(port=5005):
    server = HTTPServer(('127.0.0.1', port), SyncHandler)
    print(f"Huellitas POS Server activo en http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
