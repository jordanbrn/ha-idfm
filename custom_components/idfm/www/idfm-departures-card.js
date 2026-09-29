class IdfmDeparturesCard extends HTMLElement {
  setConfig(config) {
    if (!config || (!config.entity && !config.entities)) {
      throw new Error("idfm-departures-card: définissez 'entity' ou 'entities'.");
    }
    this._config = config;
    this._entities = config.entities || [config.entity];
    this._count = config.count || 3;
    this._groupByDirection = config.group_by_direction !== false;
    this._built = false;
    this._syncSubscriptions();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) {
      this._build();
      this._built = true;
    }
    this._update();
    this._syncSubscriptions();
  }

  // The backend only polls IDFM while at least one card showing the sensor is
  // on screen: subscribe while visible, unsubscribe as soon as it isn't.
  connectedCallback() {
    this._connected = true;
    if (!this._visibilityHandler) {
      this._visibilityHandler = () => this._syncSubscriptions();
    }
    document.addEventListener("visibilitychange", this._visibilityHandler);
    if (!this._ageTimer) this._ageTimer = setInterval(() => this._renderAge(), 1000);
    if ("IntersectionObserver" in window) {
      if (!this._observer) {
        this._observer = new IntersectionObserver((entries) => {
          this._inView = entries[entries.length - 1].isIntersecting;
          this._syncSubscriptions();
        });
      }
      this._observer.observe(this);
    } else {
      this._inView = true;
    }
    this._syncSubscriptions();
  }

  disconnectedCallback() {
    this._connected = false;
    this._inView = false;
    document.removeEventListener("visibilitychange", this._visibilityHandler);
    if (this._observer) this._observer.disconnect();
    clearInterval(this._ageTimer);
    this._ageTimer = null;
    this._syncSubscriptions();
  }

  _syncSubscriptions() {
    if (!this._subs) this._subs = new Map();
    const visible =
      this._connected && this._inView && document.visibilityState === "visible";
    const wanted = new Set(visible && this._hass && this._entities ? this._entities : []);

    for (const [entityId, unsubPromise] of this._subs) {
      if (wanted.has(entityId)) continue;
      this._subs.delete(entityId);
      unsubPromise.then((unsub) => unsub && unsub()).catch(() => {});
    }
    for (const entityId of wanted) {
      if (this._subs.has(entityId)) continue;
      this._subs.set(
        entityId,
        this._hass.connection
          .subscribeMessage(() => {}, {
            type: "idfm/departures/subscribe",
            entity_id: entityId,
          })
          .catch(() => null)
      );
    }
  }

  getCardSize() {
    return this._entities.length * (this._groupByDirection ? 4 : 2) + (this._config.title ? 1 : 0);
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

    const header = document.createElement("div");
    header.className = `card-header idfm-header${this._config.title ? "" : " no-title"}`;
    header.innerHTML = `
      <span class="idfm-title"></span>
      <button class="idfm-refresh" title="Rafraîchir les départs">
        <span class="idfm-age"></span>
        <ha-icon icon="mdi:refresh"></ha-icon>
      </button>
    `;
    header.querySelector(".idfm-title").textContent = this._config.title || "";
    this._refreshButton = header.querySelector(".idfm-refresh");
    this._refreshButton.addEventListener("click", () => this._refresh());

    const style = document.createElement("style");
    style.textContent = `
      .idfm-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .idfm-header.no-title { justify-content: flex-end; padding: 8px 12px 0; }
      .idfm-refresh {
        flex: none; display: inline-flex; align-items: center; gap: 4px;
        border: none; background: none; cursor: pointer; border-radius: 8px;
        padding: 4px 6px; font-family: inherit; font-size: 12px; font-weight: 500;
        color: var(--secondary-text-color);
      }
      .idfm-refresh:hover { background: var(--secondary-background-color, rgba(127, 127, 127, 0.1)); }
      .idfm-refresh:disabled { cursor: default; }
      .idfm-refresh ha-icon { --mdc-icon-size: 18px; }
      .idfm-refresh.spinning ha-icon { animation: idfm-spin 1s linear infinite; }
      @keyframes idfm-spin { to { transform: rotate(360deg); } }
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
      .idfm-departure-list { margin-top: 8px; display: flex; flex-direction: column; gap: 10px; }
      .idfm-direction { display: flex; align-items: center; gap: 4px; margin-bottom: 4px;
        font-size: 12px; font-weight: 600; color: var(--secondary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .idfm-direction ha-icon { --mdc-icon-size: 14px; flex: none; }
      .idfm-group-rows {
        border-radius: 10px; overflow: hidden;
        background: var(--secondary-background-color, rgba(127, 127, 127, 0.07));
      }
      .idfm-departure-row {
        display: flex; align-items: center; gap: 12px; padding: 9px 12px;
        border-bottom: 1px solid var(--divider-color);
      }
      .idfm-departure-row:last-child { border-bottom: none; }
      .idfm-departure-row.next {
        background: var(--idfm-row-accent, var(--primary-color));
      }
      .idfm-time { flex: none; min-width: 44px; font-weight: 700; font-size: 14px;
        color: var(--primary-text-color); }
      .idfm-departure-row.next .idfm-time,
      .idfm-departure-row.next .idfm-dest,
      .idfm-departure-row.next .idfm-mission,
      .idfm-departure-row.next .idfm-platform {
        color: var(--idfm-row-accent-text, var(--text-primary-color, #fff));
      }
      .idfm-mission { flex: none; font-family: var(--code-font-family, monospace);
        font-weight: 700; font-size: 12px; letter-spacing: 0.5px;
        color: var(--secondary-text-color); }
      .idfm-dest { flex: 1; min-width: 0; font-size: 13px; color: var(--secondary-text-color);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .idfm-departure-row.next .idfm-dest { opacity: 0.9; }
      .idfm-departure-row.next .idfm-platform { border-color: rgba(255, 255, 255, 0.5); }
      .idfm-platform { flex: none; font-size: 11px; font-weight: 600;
        color: var(--secondary-text-color); border: 1px solid var(--divider-color);
        border-radius: 6px; padding: 2px 6px; }
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
    card.appendChild(header);
    card.appendChild(stops);
    this.innerHTML = "";
    // Block box so the IntersectionObserver sees the card's real bounds.
    this.style.display = "block";
    this.appendChild(card);
    this._card = card;
  }

  async _refresh() {
    if (!this._hass || this._refreshButton.disabled) return;
    this._refreshButton.disabled = true;
    this._refreshButton.classList.add("spinning");
    const started = Date.now();
    try {
      await this._hass.callService("homeassistant", "update_entity", {
        entity_id: this._entities,
      });
    } catch (err) {
      // Ignored: the sensors keep their last data and the age shows it's stale.
    }
    // Spin for at least one turn so a fast answer still reads as feedback.
    setTimeout(() => {
      this._refreshButton.disabled = false;
      this._refreshButton.classList.remove("spinning");
    }, Math.max(0, 1000 - (Date.now() - started)));
  }

  // Age of the stalest stop's data, i.e. of the last real IDFM request.
  _renderAge() {
    if (!this._hass || !this._refreshButton) return;
    let oldest = null;
    for (const entityId of this._entities) {
      const fetchedAt = this._hass.states[entityId]?.attributes?.fetched_at;
      if (!fetchedAt) continue;
      const t = Date.parse(fetchedAt);
      if (oldest === null || t < oldest) oldest = t;
    }
    const label = this._refreshButton.querySelector(".idfm-age");
    if (oldest === null) {
      label.textContent = "";
      return;
    }
    const seconds = Math.max(0, Math.round((Date.now() - oldest) / 1000));
    label.textContent =
      seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min`;
  }

  _groupDepartures(departures) {
    // Departures come sorted by time, so groups end up ordered by their next departure.
    const groups = new Map();
    for (const d of departures) {
      const key = this._groupByDirection ? d.direction || d.destination || "" : "";
      if (!groups.has(key)) groups.set(key, []);
      const group = groups.get(key);
      if (group.length < this._count) group.push(d);
    }
    return [...groups.entries()];
  }

  _renderDeparture(d, next) {
    return `
      <div class="idfm-departure-row${next ? " next" : ""}">
        <span class="idfm-time">${d.formatted || d.minutes + "min"}</span>
        ${d.mission ? `<span class="idfm-mission">${d.mission}</span>` : ""}
        <span class="idfm-dest">${d.destination || ""}</span>
        ${d.platform ? `<span class="idfm-platform">${d.platform}</span>` : ""}
      </div>`;
  }

  _update() {
    if (!this._hass) return;
    this._renderAge();

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
      list.style.setProperty("--idfm-row-accent", color);
      list.style.setProperty("--idfm-row-accent-text", textColor);
      const groups = this._groupDepartures(attrs.departures || []);
      if (groups.length === 0) {
        list.innerHTML =
          '<div class="idfm-group-rows"><div class="idfm-empty">Aucun départ prévu</div></div>';
      } else {
        // A direction header is only worth its space when there's more than one.
        const showHeaders = groups.length > 1;
        list.innerHTML = groups
          .map(
            ([direction, departures]) => `
          <div class="idfm-group">
            ${
              showHeaders && direction
                ? `<div class="idfm-direction"><ha-icon icon="mdi:arrow-right"></ha-icon>${direction}</div>`
                : ""
            }
            <div class="idfm-group-rows">
              ${departures.map((d, i) => this._renderDeparture(d, i === 0)).join("")}
            </div>
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
      { name: "group_by_direction", default: true, selector: { boolean: {} } },
    ];
    this._form.computeLabel = (schema) => {
      const labels = {
        title: "Titre",
        entities: "Stations à afficher",
        count: "Nombre de départs par direction",
        group_by_direction: "Séparer par direction",
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
