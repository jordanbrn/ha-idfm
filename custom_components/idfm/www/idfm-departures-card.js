class IdfmDeparturesCard extends HTMLElement {
  setConfig(config) {
    if (!config || (!config.entity && !config.entities)) {
      throw new Error("idfm-departures-card: définissez 'entity' ou 'entities'.");
    }
    this._config = config;
    this._entities = config.entities || [config.entity];
    this._count = config.count || 3;
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
    }
    this._update();
  }

  getCardSize() {
    return this._entities.length + (this._config.title ? 1 : 0);
  }

  static getStubConfig() {
    return { entities: [] };
  }

  static _modeIcon(mode) {
    switch (mode) {
      case "metro":
        return "mdi:subway-variant";
      case "rail":
        return "mdi:train";
      case "tram":
        return "mdi:tram";
      case "bus":
        return "mdi:bus";
      default:
        return "mdi:train";
    }
  }

  _build() {
    const card = document.createElement("ha-card");
    if (this._config.title) card.header = this._config.title;

    const style = document.createElement("style");
    style.textContent = `
      .idfm-stops { padding: 4px 16px 16px; display: flex; flex-direction: column; gap: 16px; }
      .idfm-stop-header { display: flex; align-items: center; gap: 8px; }
      .idfm-stop-header ha-icon { color: var(--secondary-text-color); }
      .idfm-stop-name { font-weight: 600; font-size: 15px; color: var(--primary-text-color); }
      .idfm-stop-sub { font-size: 12px; color: var(--secondary-text-color); margin-left: auto; }
      .idfm-chips { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
      .idfm-chip {
        background: var(--secondary-background-color, rgba(127,127,127,0.1));
        border-radius: 14px; padding: 6px 14px; font-size: 14px; font-weight: 600;
        color: var(--primary-text-color);
      }
      .idfm-chip:first-child { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .idfm-chip-dest { font-size: 11px; font-weight: 400; opacity: 0.8; display: block; }
      .idfm-empty-chip { color: var(--secondary-text-color); font-size: 13px; }
    `;

    const stops = document.createElement("div");
    stops.className = "idfm-stops";

    this._rows = {};
    for (const entityId of this._entities) {
      const row = document.createElement("div");
      row.className = "idfm-stop";
      row.innerHTML = `
        <div class="idfm-stop-header">
          <ha-icon icon="mdi:train"></ha-icon>
          <span class="idfm-stop-name"></span>
          <span class="idfm-stop-sub"></span>
        </div>
        <div class="idfm-chips"></div>
      `;
      stops.appendChild(row);
      this._rows[entityId] = row;
    }

    card.appendChild(style);
    card.appendChild(stops);
    this.innerHTML = "";
    this.appendChild(card);
    this._card = card;
  }

  _update() {
    if (!this._hass) return;

    for (const entityId of this._entities) {
      const row = this._rows[entityId];
      const stateObj = this._hass.states[entityId];
      if (!row) continue;

      if (!stateObj) {
        row.querySelector(".idfm-stop-name").textContent = entityId;
        row.querySelector(".idfm-chips").innerHTML =
          '<span class="idfm-empty-chip">Entité indisponible</span>';
        continue;
      }

      const attrs = stateObj.attributes || {};
      row.querySelector("ha-icon").setAttribute(
        "icon",
        IdfmDeparturesCard._modeIcon(attrs.mode)
      );
      row.querySelector(".idfm-stop-name").textContent =
        attrs.stop_name || stateObj.attributes.friendly_name || entityId;
      row.querySelector(".idfm-stop-sub").textContent =
        attrs.line_name || attrs.direction || attrs.destination || "";

      const chips = row.querySelector(".idfm-chips");
      const departures = (attrs.departures || []).slice(0, this._count);
      if (departures.length === 0) {
        chips.innerHTML = '<span class="idfm-empty-chip">Aucun départ prévu</span>';
      } else {
        chips.innerHTML = departures
          .map(
            (d) => `
          <div class="idfm-chip">
            ${d.formatted || d.minutes + "min"}
            ${d.destination ? `<span class="idfm-chip-dest">${d.destination}</span>` : ""}
          </div>`
          )
          .join("");
      }
    }
  }
}

if (!customElements.get("idfm-departures-card")) {
  customElements.define("idfm-departures-card", IdfmDeparturesCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "idfm-departures-card",
    name: "IDFM - Prochains départs",
    description: "Affiche les prochains départs d'une ou plusieurs stations IDFM.",
  });
}
