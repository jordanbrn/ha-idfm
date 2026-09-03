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
    return this._entities.length * 2 + (this._config.title ? 1 : 0);
  }

  static getStubConfig() {
    return { entities: [], count: 3 };
  }

  static getConfigElement() {
    return document.createElement("idfm-departures-card-editor");
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
      badge.innerHTML = `<ha-icon icon="${IdfmDeparturesCard._modeIcon(mode)}"></ha-icon>`;
    }
  }

  _build() {
    const card = document.createElement("ha-card");
    if (this._config.title) card.header = this._config.title;

    const style = document.createElement("style");
    style.textContent = `
      .idfm-stops { padding: 4px 16px 16px; display: flex; flex-direction: column; gap: 20px; }
      .idfm-stop-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
      .idfm-stop-name { font-weight: 600; font-size: 15px; color: var(--primary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .idfm-badge {
        flex: none; width: 32px; height: 32px; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 13px;
      }
      .idfm-badge ha-icon { --mdc-icon-size: 16px; }
      .idfm-departure-list {
        margin-top: 8px; border-radius: 10px; overflow: hidden;
        background: var(--secondary-background-color, rgba(127, 127, 127, 0.07));
      }
      .idfm-departure-row {
        display: flex; align-items: center; gap: 12px; padding: 9px 12px;
        border-bottom: 1px solid var(--divider-color);
      }
      .idfm-departure-row:last-child { border-bottom: none; }
      .idfm-departure-row.next { background: var(--primary-color); }
      .idfm-time { flex: none; min-width: 44px; font-weight: 700; font-size: 14px;
        color: var(--primary-text-color); }
      .idfm-departure-row.next .idfm-time,
      .idfm-departure-row.next .idfm-dest { color: var(--text-primary-color, #fff); }
      .idfm-dest { flex: 1; min-width: 0; font-size: 13px; color: var(--secondary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .idfm-departure-row.next .idfm-dest { opacity: 0.9; }
      .idfm-platform { flex: none; font-size: 11px; font-weight: 600;
        color: var(--secondary-text-color); border: 1px solid var(--divider-color);
        border-radius: 6px; padding: 2px 6px; }
      .idfm-departure-row.next .idfm-platform {
        color: var(--text-primary-color, #fff); border-color: rgba(255, 255, 255, 0.5); }
      .idfm-empty { padding: 10px 12px; color: var(--secondary-text-color); font-size: 13px; }
    `;

    const stops = document.createElement("div");
    stops.className = "idfm-stops";

    this._rows = {};
    for (const entityId of this._entities) {
      const row = document.createElement("div");
      row.className = "idfm-stop";
      row.innerHTML = `
        <div class="idfm-stop-header">
          <span class="idfm-stop-name"></span>
          <div class="idfm-badge"></div>
        </div>
        <div class="idfm-departure-list"></div>
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
        row.querySelector(".idfm-departure-list").innerHTML =
          '<div class="idfm-empty">Entité indisponible</div>';
        continue;
      }

      const attrs = stateObj.attributes || {};
      const shortName = attrs.short_name || attrs.line_name || "";
      const color = attrs.color || "#0064B0";
      const textColor = attrs.text_color || "#FFFFFF";

      row.querySelector(".idfm-stop-name").textContent =
        attrs.stop_name || attrs.friendly_name || entityId;

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

      const list = row.querySelector(".idfm-departure-list");
      const departures = (attrs.departures || []).slice(0, this._count);
      if (departures.length === 0) {
        list.innerHTML = '<div class="idfm-empty">Aucun départ prévu</div>';
      } else {
        list.innerHTML = departures
          .map(
            (d, i) => `
          <div class="idfm-departure-row${i === 0 ? " next" : ""}">
            <span class="idfm-time">${d.formatted || d.minutes + "min"}</span>
            <span class="idfm-dest">${d.destination || ""}</span>
            ${d.platform ? `<span class="idfm-platform">${d.platform}</span>` : ""}
          </div>`
          )
          .join("");
      }
    }
  }
}

class IdfmDeparturesCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._ensureForm();
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _ensureForm() {
    if (this._form) return;
    this._form = document.createElement("ha-form");
    this._form.schema = [
      { name: "title", selector: { text: {} } },
      {
        name: "entities",
        selector: { entity: { multiple: true, filter: { domain: "sensor" } } },
      },
      { name: "count", selector: { number: { min: 1, max: 10, mode: "box" } } },
    ];
    this._form.computeLabel = (schema) => {
      const labels = {
        title: "Titre",
        entities: "Stations à afficher",
        count: "Nombre de départs par station",
      };
      return labels[schema.name] || schema.name;
    };
    this._form.addEventListener("value-changed", (ev) => {
      this._config = ev.detail.value;
      this.dispatchEvent(
        new CustomEvent("config-changed", { detail: { config: this._config } })
      );
    });
    this.appendChild(this._form);
  }

  _render() {
    if (!this._form) return;
    this._form.hass = this._hass;
    this._form.data = this._config;
  }
}

if (!customElements.get("idfm-departures-card-editor")) {
  customElements.define("idfm-departures-card-editor", IdfmDeparturesCardEditor);
}

if (!customElements.get("idfm-departures-card")) {
  customElements.define("idfm-departures-card", IdfmDeparturesCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "idfm-departures-card",
    name: "IDFM - Prochains départs",
    description: "Affiche les prochains départs d'une ou plusieurs stations IDFM.",
    preview: false,
    documentationURL: "https://github.com/jordanbrn/ha-idfm",
  });
}
