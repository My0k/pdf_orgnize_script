#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Renombrador de PDFs por "folio" según CSV.

CSV esperado (cabeceras, sin importar mayúsculas/minúsculas):
path, folio, folio_correcto

Ejemplo:
path,folio,folio_correcto
2017\\01\\traspaso,17020026,17010026
2017\\04\\egreso,20170413,17040075
2017\\04\\egreso,20170421,17040074
"""

import os
import sys
import csv
from pathlib import Path

DEFAULT_BASE = r"C:\Users\Estacion 1\OneDrive\Documentos\indexanter\ENTREGABLES"

def ensure_pdf(name: str) -> str:
    name = (name or "").strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        sys.exit(1)

def pick_csv(base_dir: Path) -> Path:
    csvs = sorted(base_dir.glob("*.csv"))
    if not csvs:
        print(f"No se encontraron archivos .csv en la carpeta raíz:\n{base_dir}")
        sys.exit(1)

    print("\n== CSVs disponibles en la carpeta raíz ==")
    for i, p in enumerate(csvs, 1):
        print(f"[{i}] {p.name}")

    while True:
        choice = ask("\nElige el número del CSV a usar: ").strip()
        if not choice.isdigit():
            print("Ingresa un número válido.")
            continue
        idx = int(choice)
        if 1 <= idx <= len(csvs):
            return csvs[idx - 1]
        print("Opción fuera de rango.")

def sniff_csv_dialect(fp) -> csv.Dialect:
    sample = fp.read(2048)
    fp.seek(0)
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=[",", ";", "\t", "|"])
        # a veces no detecta headers correctamente; igual validamos luego
        return dialect
    except Exception:
        # fallback razonable (muchos CSV en Chile vienen con coma o tab)
        class SimpleDialect(csv.Dialect):
            delimiter = "," if "," in sample else ("\t" if "\t" in sample else ";")
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return SimpleDialect()

def load_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        dialect = sniff_csv_dialect(fp)
        reader = csv.DictReader(fp, dialect=dialect)
        # normalizar nombres de columnas a minúsculas sin espacios
        field_map = { (f or "").strip().lower(): f for f in (reader.fieldnames or []) }

        required = ["path", "folio", "folio_correcto"]
        missing = [r for r in required if r not in field_map]
        if missing:
            # intentar tolerar variantes como "folio correcto", etc.
            alt_map = {}
            for k, orig in field_map.items():
                k2 = k.replace(" ", "").replace("-", "_")
                alt_map[k2] = orig
            remapped = {}
            for r in required:
                if r in field_map:
                    remapped[r] = field_map[r]
                else:
                    # buscar coincidencias aproximadas simples
                    if r == "folio_correcto":
                        for cand in ("folio_correcto", "foliocorrecto", "folio-correcto", "folio correcto"):
                            c2 = cand.replace(" ", "").replace("-", "_")
                            if c2 in alt_map:
                                remapped[r] = alt_map[c2]
                                break
            missing2 = [r for r in required if r not in remapped]
            if missing2:
                print("ERROR: El CSV no contiene las columnas requeridas:")
                print("Requeridas:", ", ".join(required))
                print("Encontradas:", ", ".join(reader.fieldnames or []))
                sys.exit(1)
            field_map = remapped

        rows = []
        for i, raw in enumerate(reader, 2):  # línea 2 en adelante (después de header)
            try:
                rel_path = (raw[field_map["path"]] or "").strip()
                folio = (raw[field_map["folio"]] or "").strip()
                folio_ok = (raw[field_map["folio_correcto"]] or "").strip()
                if not (rel_path and folio and folio_ok):
                    print(f"Fila {i}: datos incompletos; se omite.")
                    continue
                rows.append({
                    "rel_path": rel_path,
                    "folio": folio,
                    "folio_ok": folio_ok,
                    "rownum": i
                })
            except KeyError as e:
                print(f"Fila {i}: falta columna {e}; se omite.")
        return rows

def main():
    print("=== Renombrador de PDFs por folio ===")
    base_in = ask(f"Carpeta base (ENTER para usar por defecto):\n[{DEFAULT_BASE}]\n> ").strip()
    base_dir = Path(base_in) if base_in else Path(DEFAULT_BASE)

    if not base_dir.exists() or not base_dir.is_dir():
        print(f"ERROR: La carpeta no existe o no es un directorio:\n{base_dir}")
        sys.exit(1)

    csv_path = pick_csv(base_dir)
    print(f"\nUsando CSV: {csv_path.name}")

    rows = load_rows(csv_path)
    if not rows:
        print("No hay filas válidas en el CSV.")
        sys.exit(0)

    # Preparar plan de cambios (preview)
    print("\n== PREVIEW de cambios ==")
    plan = []
    n_exists = n_missing = n_conflicts = 0

    for r in rows:
        folder = (base_dir / Path(r["rel_path"])).resolve()
        src_name = ensure_pdf(r["folio"])
        dst_name = ensure_pdf(r["folio_ok"])
        src = folder / src_name
        dst = folder / dst_name

        status = []
        if src.exists():
            status.append("OK: origen encontrado")
            n_exists += 1
            if dst.exists() and src.resolve() != dst.resolve():
                status.append("ATENCIÓN: destino ya existe (conflicto)")
                n_conflicts += 1
        else:
            status.append("FALTA: origen NO existe")
            n_missing += 1

        plan.append({
            "rownum": r["rownum"],
            "src": src,
            "dst": dst,
            "can_move": src.exists() and (not dst.exists() or src.resolve() == dst.resolve())
        })

        print(f"- Fila {r['rownum']}:")
        print(f"  {src}  ->  {dst}")
        for s in status:
            print(f"    • {s}")

    print("\nResumen:")
    print(f"  - Orígenes encontrados: {n_exists}")
    print(f"  - Orígenes faltantes:   {n_missing}")
    print(f"  - Conflictos destino:   {n_conflicts} (se omiten por seguridad)")

    go = ask('\n¿Continuar con renombrar folios? Presiona "1" para aplicar, cualquier otra tecla para salir: ').strip()
    if go != "1":
        print("Operación cancelada. No se realizaron cambios.")
        sys.exit(0)

    print("\n== Aplicando cambios ==")
    moved = skipped = 0
    for item in plan:
        src, dst = item["src"], item["dst"]
        if not item["can_move"]:
            print(f"[OMITIDO] {src.name} -> {dst.name}  (no se puede mover: falta origen o destino en conflicto)")
            skipped += 1
            continue

        try:
            # Si ya es el mismo archivo (mismo nombre), no hacer nada
            if src.resolve() == dst.resolve():
                print(f"[YA OK]  {src.name}  (nombre ya coincide)")
                continue

            # Por seguridad, no sobreescribimos un destino existente distinto
            if dst.exists():
                print(f"[OMITIDO] {src.name} -> {dst.name}  (destino existe)")
                skipped += 1
                continue

            src.rename(dst)  # mueve/renombra
            print(f"[RENOMBRADO] {src.name} -> {dst.name}")
            moved += 1
        except Exception as e:
            print(f"[ERROR] {src} -> {dst}: {e}")
            skipped += 1

    print("\n== Resultado ==")
    print(f"  Renombrados: {moved}")
    print(f"  Omitidos:    {skipped}")
    print("\nListo.")

if __name__ == "__main__":
    main()
