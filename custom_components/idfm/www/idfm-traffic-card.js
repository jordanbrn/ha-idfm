class IdfmTrafficCard extends HTMLElement {
  setConfig(config) {
    if (!config || (!config.entity && !config.entities)) {
      throw new Error("idfm-traffic-card: définissez 'entity' ou 'entities'.");
    }
    this._config = config;
    this._entities = config.entities || [config.entity];
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

  _build() {
    const card = document.createElement("ha-card");
    if (this._config.title) card.header = this._config.title;

    const style = document.createElement("style");
    style.textContent = `
      .idfm-list { padding: 4px 16px 16px; display: flex; flex-direction: column; gap: 10px; }
      .idfm-row { display: flex; align-items: flex-start; gap: 12px; }
      .idfm-badge {
        flex: none; width: 40px; height: 40px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 15px; overflow: hidden;
      }
      .idfm-badge ha-icon { --mdc-icon-size: 20px; }
      .idfm-body { flex: 1; min-width: 0; border-left: 3px solid var(--idfm-status-color, var(--divider-color));
        padding-left: 10px; }
      .idfm-line { font-weight: 600; color: var(--primary-text-color); font-size: 14px; }
      .idfm-message { color: var(--secondary-text-color); font-size: 13px; margin-top: 2px;
        white-space: normal; word-break: break-word; }
      .idfm-empty { padding: 16px; color: var(--secondary-text-color); }
    `;

    const list = document.createElement("div");
    list.className = "idfm-list";

    this._rows = {};
    for (const entityId of this._entities) {
      const row = document.createElement("div");
      row.className = "idfm-row";
      row.innerHTML = `
        <div class="idfm-badge"></div>
        <div class="idfm-body">
          <div class="idfm-line"></div>
          <div class="idfm-message"></div>
        </div>
      `;
      list.appendChild(row);
      this._rows[entityId] = row;
    }

    card.appendChild(style);
    card.appendChild(list);
    this.innerHTML = "";
    this.appendChild(card);
    this._card = card;
    this._list = list;
  }

  static _statusColor(state) {
    switch (state) {
      case "normal":
        return "#2e7d32";
      case "info":
        return "#0288d1";
      case "perturbe":
        return "#ed6c02";
      case "bloque":
        return "#c62828";
      default:
        return "var(--divider-color)";
    }
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

  _renderImageBadge(badge, src, alt) {
    badge.style.background = "transparent";
    badge.style.overflow = "visible";
    badge.innerHTML = `<img src="${src}" alt="${alt || ""}" style="width:100%;height:100%;object-fit:contain;" />`;
  }

  _renderTextBadge(badge, shortName, color, textColor, mode) {
    badge.style.background = color;
    badge.style.color = textColor;
    badge.style.overflow = "hidden";
    if (shortName && shortName.length <= 3) {
      badge.innerHTML = shortName;
    } else {
      badge.innerHTML = `<ha-icon icon="${IdfmTrafficCard._modeIcon(mode)}"></ha-icon>`;
    }
  }

  _update() {
    if (!this._hass) return;

    for (const entityId of this._entities) {
      const row = this._rows[entityId];
      const stateObj = this._hass.states[entityId];
      if (!row) continue;

      if (!stateObj) {
        row.querySelector(".idfm-line").textContent = entityId;
        row.querySelector(".idfm-message").textContent = "Entité indisponible";
        continue;
      }

      const attrs = stateObj.attributes || {};
      const shortName = attrs.short_name || attrs.line_name || stateObj.entity_id;
      const color = attrs.color || "#0064B0";
      const textColor = attrs.text_color || "#FFFFFF";
      const statusColor = IdfmTrafficCard._statusColor(stateObj.state);

      const badge = row.querySelector(".idfm-badge");
      const picture = attrs.entity_picture;
      if (picture) {
        const src = this._hass.hassUrl ? this._hass.hassUrl(picture) : picture;
        this._renderImageBadge(badge, src, shortName);
        const img = badge.querySelector("img");
        img.addEventListener(
          "error",
          () => this._renderTextBadge(badge, shortName, color, textColor, attrs.mode),
          { once: true }
        );
      } else {
        this._renderTextBadge(badge, shortName, color, textColor, attrs.mode);
      }

      row.querySelector(".idfm-line").textContent = attrs.line_name || shortName;
      row.querySelector(".idfm-message").textContent = attrs.message || "Trafic normal";
      row.querySelector(".idfm-body").style.setProperty("--idfm-status-color", statusColor);
      row.title = attrs.title || "";
    }
  }
}

if (!customElements.get("idfm-traffic-card")) {
  customElements.define("idfm-traffic-card", IdfmTrafficCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "idfm-traffic-card",
    name: "IDFM - État du trafic",
    description: "Affiche l'état du trafic d'une ou plusieurs lignes IDFM.",
    preview: false,
    documentationURL: "https://github.com/jordanbrn/ha-idfm",
  });
}
