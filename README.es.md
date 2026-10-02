# ✈️ FareHunter

[English](README.md) · [Português](README.pt-BR.md) · **Español**

Un plugin para Claude que encuentra la **forma más barata de volar**. Compara tarifas en efectivo, fechas cercanas, millas que ya tienes, compra de millas y transferencia de puntos de la tarjeta. El resultado sale en tu moneda, con los enlaces para que compres o emitas tú mismo.

- Cualquier país y moneda. Más de 30 programas de millas (LifeMiles, Copa, Aeroméxico, United, Aeroplan, Flying Blue, Avios, LATAM Pass…) y puntos de tarjeta (Amex, Chase, Citi…).
- Te habla en tu idioma (Español, Português, English…).
- Corre en tu computadora, con tus propias cuentas. **Nunca compra, no emite y nunca pide contraseñas**.

## Instalar

| | |
|---|---|
| 🖥️ **[Claude Desktop](docs/install/claude-desktop.es.md)** | Mac y Windows, sin terminal |
| ⌨️ **[Claude Code](docs/install/claude-code.es.md)** | Terminal: Mac, Windows y Linux |

## Usar

| Escribe | Para qué |
|---|---|
| `/farehunter:profile` | Cuéntale una vez tus aeropuertos y programas de millas |
| `/farehunter:search Ciudad de México a Madrid 20/11, vuelta 27/11` | Busca la forma más barata; también puedes pedirlo con tus palabras |
| `/farehunter:miles` | Actualiza cuánto vale cada milla y las promociones vigentes |
| `/farehunter:setup` | Revisa la instalación cuando algo falla |

## Bueno saber

- **Saldos:** pregunta tus saldos en cada búsqueda, porque cambian todo el tiempo. No se guarda nada sobre tus saldos.
- **Precios:** cambian hasta la compra. Los canjes marcados como **caché** deben verificarse en el sitio del programa.
- **Tus datos:** quedan en `~/.farehunter/`, en tu computadora.
- **Extras opcionales:** [Seats.aero Pro](https://seats.aero) permite buscar canjes más allá de 60 días. LATAM Pass requiere que inicies sesión tú mismo en el sitio de LATAM.

---
[Cómo funciona](docs/desenvolvimento.md) · [Investigación y fuentes](docs/research.md) · [Decisiones](docs/decisoes.md) · licencia MIT
