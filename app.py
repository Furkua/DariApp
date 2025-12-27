import re
import asyncio
import streamlit as st
from playwright.async_api import async_playwright

URL = "https://www.bancoestado.cl/bancoestado/simulaciones/comercio/simule_1.asp"


async def extraer_resultado(page) -> str:
    loc = page.get_by_text(re.compile(r"\bResultado\b", re.I)).first
    await loc.wait_for(timeout=20000)

    box = loc.locator(
        "xpath=ancestor-or-self::*[self::p or self::div or self::li or self::td][1]"
    )
    try:
        txt = (await box.inner_text()).strip()
    except Exception:
        txt = (await loc.inner_text()).strip()

    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if "resultado" in line.lower():
            if ":" in line:
                return line.split(":", 1)[1].strip()
            if i + 1 < len(lines):
                return lines[i + 1].strip()

    body = (await page.locator("body").inner_text()).splitlines()
    body = [l.strip() for l in body if l.strip()]
    for i, line in enumerate(body):
        if "resultado" in line.lower():
            if ":" in line:
                return line.split(":", 1)[1].strip()
            if i + 1 < len(body):
                return body[i + 1].strip()

    raise RuntimeError("No pude localizar el valor de 'Resultado'.")


async def simular(operacion_texto: str, monto: str, debug: bool) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context = await browser.new_context(
            locale="es-CL",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "es-CL,es;q=0.9,en;q=0.8"},
        )

        page = await context.new_page()
        resp = await page.goto(URL, wait_until="domcontentloaded", timeout=45000)

        if resp is None:
            await browser.close()
            raise RuntimeError("No hubo respuesta HTTP al cargar la página.")
        if resp.status >= 400:
            await browser.close()
            raise RuntimeError(f"HTTP {resp.status} al cargar la página.")

        await page.wait_for_timeout(800)

        # CLAVE: NO se clickea por texto. Se selecciona el radio por role/name.
        radio = page.get_by_role("radio", name=re.compile(operacion_texto, re.I))
        if await radio.count() > 0:
            await radio.first.check()
        else:
            # Fallback: click al label asociado
            lbl = page.get_by_label(re.compile(operacion_texto, re.I))
            if await lbl.count() > 0:
                await lbl.first.click(force=True)
            else:
                if debug:
                    html = await page.content()
                    await browser.close()
                    raise RuntimeError(
                        f"No encuentro radio/label para '{operacion_texto}'. "
                        f"HTML (primeros 1500 chars):\n{html[:1500]}"
                    )
                await browser.close()
                raise RuntimeError(f"No encuentro selector para '{operacion_texto}'.")

        await page.get_by_label(re.compile(r"Monto en US", re.I)).fill(monto)

        # Submit robusto
        submit = page.locator("input[type=submit], button[type=submit]")
        if await submit.count() > 0:
            await submit.first.click()
        else:
            # Fallback por texto
            for btn in ("Simular", "Continuar", "Siguiente", "Aceptar"):
                b = page.get_by_role("button", name=re.compile(btn, re.I))
                if await b.count() > 0:
                    await b.first.click()
                    break
            else:
                if debug:
                    html = await page.content()
                    await browser.close()
                    raise RuntimeError(
                        "No encontré botón submit. "
                        f"HTML (primeros 1500 chars):\n{html[:1500]}"
                    )
                await browser.close()
                raise RuntimeError("No encontré botón submit.")

        await page.wait_for_load_state("domcontentloaded", timeout=45000)

        resultado = await extraer_resultado(page)
        await browser.close()
        return resultado


async def correr(monto: str, debug: bool):
    compra = await simular("Cliente Compra", monto, debug)
    vende = await simular("Cliente Vende", monto, debug)
    return compra, vende


def run(coro):
    """
    Streamlit puede correr con loop activo dependiendo del runtime.
    Esto evita los problemas típicos de asyncio.run().
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
    except RuntimeError:
        pass
    return asyncio.run(coro)


st.set_page_config(page_title="USD Simulator Bot", layout="centered")
st.title("USD Simulator Bot (Compra/Vende)")

monto = st.text_input("Monto en USD", value="1")
debug = st.checkbox("Debug (muestra HTML si falla)", value=False)

if st.button("Ejecutar"):
    with st.spinner("Consultando..."):
        compra, vende = run(correr(monto=monto, debug=debug))

    st.write(f'Compra "{compra}"')
    st.write(f'Vende "{vende}"')
