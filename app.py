import streamlit as st
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.bancoestado.cl/bancoestado/simulaciones/comercio/simule_1.asp"

async def extraer_resultado(page) -> str:
    loc = page.get_by_text("Resultado", exact=False).first
    await loc.wait_for(timeout=8000)

    box = loc.locator("xpath=ancestor-or-self::*[self::p or self::div or self::li or self::td][1]")
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

async def simular(operacion_texto: str, monto: str = "1") -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        await page.goto(URL, wait_until="domcontentloaded")

        await page.get_by_text(operacion_texto, exact=False).click()
        await page.get_by_label("Monto en US$", exact=False).fill(monto)

        for btn in ("Simular", "Continuar", "Siguiente", "Aceptar"):
            b = page.get_by_role("button", name=btn)
            if await b.count() > 0:
                await b.first.click()
                break
        else:
            submit = page.locator("input[type=submit], button[type=submit]")
            if await submit.count() == 0:
                await browser.close()
                raise RuntimeError("No encontré botón para ejecutar la simulación.")
            await submit.first.click()

        await page.wait_for_load_state("domcontentloaded")
        resultado = await extraer_resultado(page)
        await browser.close()
        return resultado

async def correr():
    compra = await simular("Cliente Compra", "1")
    vende = await simular("Cliente Vende", "1")
    return compra, vende

st.title("BancoEstado USD Bot (Compra/Vende)")

if st.button("Ejecutar"):
    with st.spinner("Consultando simulador..."):
        compra, vende = asyncio.run(correr())
    st.write(f'Compra "{compra}"')
    st.write(f'Vende "{vende}"')
