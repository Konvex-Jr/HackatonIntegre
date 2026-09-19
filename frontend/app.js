    (function () {
      "use strict";

      /* ============ constants ============ */
      var PROTOCOLS = [
        { id: "mms", label: "MMS", full: "IEC 61850 MMS" },
        { id: "dnp3", label: "DNP3", full: "DNP3" },
        { id: "modbus", label: "Modbus", full: "Modbus" },
        { id: "opcua", label: "OPC UA", full: "OPC UA" }
      ];
      var PROTO_FULL = {}; PROTOCOLS.forEach(function (p) { PROTO_FULL[p.id] = p.full; });
      var PROTO_LABEL = {}; PROTOCOLS.forEach(function (p) { PROTO_LABEL[p.id] = p.label; });
      var PROTO_COLOR = { mms: "#4FD1C5", dnp3: "#5B9EF2", modbus: "#F2B84B", opcua: "#3ED598" };
      var STATUS_META = {
        ok: { label: "OK — sem perdas", color: "var(--good)", dim: "var(--good-dim)" },
        perda: { label: "Com perda de metadado", color: "var(--warn)", dim: "var(--warn-dim)" },
        falha_comm: { label: "Falha de comunicação", color: "var(--bad)", dim: "var(--bad-dim)" },
        erro: { label: "Erro / config inválida", color: "var(--bad)", dim: "var(--bad-dim)" },
        info: { label: "Informação do sistema", color: "var(--info)", dim: "var(--info-dim)" }
      };
      var KIND_LABEL = { convert: "Conversão", info: "Informação", error: "Erro" };

      var DATA_TYPES = ["float", "int", "bool", "string"];
      var KNOWN_UNITS = [
        { v: "", label: "(adimensional)" },
        { v: "V", label: "V — tensão" },
        { v: "kV", label: "kV — tensão" },
        { v: "A", label: "A — corrente" },
        { v: "kA", label: "kA — corrente" },
        { v: "W", label: "W — potência" },
        { v: "kW", label: "kW — potência" },
        { v: "Hz", label: "Hz — frequência" }
      ];
      var VALIDITY_OPTIONS = [
        { v: "", label: "(não informar)" },
        { v: "good", label: "good" },
        { v: "invalid", label: "invalid" },
        { v: "questionable", label: "questionable" }
      ];
      var QUALITY_FLAGS = ["overflow", "out_of_range", "forced", "substituted", "test", "comm_lost", "stale", "config_error"];

      /* ============ tiny helpers ============ */
      function el(tag, attrs, children) {
        var node = document.createElement(tag);
        attrs = attrs || {};
        Object.keys(attrs).forEach(function (k) {
          if (k === "class") node.className = attrs[k];
          else if (k === "html") node.innerHTML = attrs[k];
          else if (k === "text") node.textContent = attrs[k];
          else if (k.indexOf("on") === 0 && typeof attrs[k] === "function") node.addEventListener(k.slice(2), attrs[k]);
          else node.setAttribute(k, attrs[k]);
        });
        (children || []).forEach(function (c) { if (c) node.appendChild(c); });
        return node;
      }
      function fmtTime(tsSeconds) {
        try {
          var d = new Date(tsSeconds * 1000);
          return d.toLocaleString("pt-BR", { hour12: false });
        } catch (e) { return ""; }
      }
      function fmtIso(iso) {
        try {
          var d = new Date(iso);
          return d.toLocaleString("pt-BR", { hour12: false });
        } catch (e) { return iso; }
      }
      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
        });
      }

      /* ============ toast ============ */
      function toast(message, kind) {
        var region = document.getElementById("toast-region");
        var node = el("div", { class: "toast" + (kind ? " " + kind : ""), text: message });
        region.appendChild(node);
        setTimeout(function () { node.remove(); }, 4200);
      }

      /* ============ api layer ============ */
      function ApiError(message, status) {
        this.message = message; this.status = status; this.name = "ApiError";
      }
      ApiError.prototype = Object.create(Error.prototype);

      function api(method, path, body) {
        var opts = { method: method, headers: {} };
        if (body !== undefined) {
          opts.headers["Content-Type"] = "application/json";
          opts.body = JSON.stringify(body);
        }
        return fetch(path, opts).catch(function () {
          throw new ApiError("Não foi possível falar com o servidor (" + path + "). O backend está rodando?", 0);
        }).then(function (res) {
          return res.text().then(function (text) {
            var data = null;
            if (text) {
              try { data = JSON.parse(text); } catch (e) { data = text; }
            }
            if (!res.ok) {
              var msg = (data && typeof data === "object" && "detail" in data) ? data.detail
                : (typeof data === "string" && data) ? data
                  : ("Erro " + res.status);
              throw new ApiError(msg, res.status);
            }
            return data;
          });
        });
      }
      function apiGet(path) { return api("GET", path); }
      function apiPost(path, body) { return api("POST", path, body === undefined ? {} : body); }
      function apiDelete(path) { return api("DELETE", path); }

      function reportApiError(err, fallback) {
        var msg = (err && err.message) ? err.message : (fallback || "Ocorreu um erro inesperado.");
        toast(msg, "error");
      }

      /* ============ view switching ============ */
      var activePolls = {};
      function clearPoll(name) { if (activePolls[name]) { clearInterval(activePolls[name]); delete activePolls[name]; } }

      var VIEW_INIT = {
        painel: initPainel,
        dashboard: initDashboard,
        conversor: initConversor,
        mapeamentos: initMapeamentos,
        historico: initHistorico
      };

      function showView(name) {
        document.querySelectorAll(".tab").forEach(function (t) {
          t.classList.toggle("active", t.dataset.view === name);
          t.setAttribute("aria-selected", t.dataset.view === name ? "true" : "false");
        });
        document.querySelectorAll(".view").forEach(function (v) {
          v.classList.toggle("active", v.id === "view-" + name);
        });
        clearPoll("adapters");
        clearPoll("dashboard");
        clearPoll("logs");
        if (VIEW_INIT[name]) VIEW_INIT[name]();
        location.hash = name;
      }

      document.querySelectorAll(".tab").forEach(function (t) {
        t.addEventListener("click", function () { showView(t.dataset.view); });
      });

      /* ============ shared renderers ============ */
      function circuitPill(state) {
        var map = {
          closed: { cls: "good", label: "operando" },
          open: { cls: "bad", label: "circuito aberto" },
          half_open: { cls: "warn", label: "testando reconexão" }
        };
        var m = map[state] || { cls: "off", label: state || "desconhecido" };
        return el("span", { class: "pill " + m.cls, text: m.label });
      }

      function protocolBadge(id) {
        return el("span", { class: "badge-proto", text: PROTO_LABEL[id] || id });
      }

      function qualityInline(q) {
        var flags = (q.flags && q.flags.length) ? q.flags.join(",") : "-";
        var cls = q.validity === "good" ? "good" : (q.validity === "questionable" ? "warn" : "bad");
        return el("span", { class: "pill " + cls, text: q.validity + "[" + flags + "]" });
      }

      function barList(container, data) {
        container.innerHTML = "";
        if (!data || !data.length) {
          container.appendChild(el("div", { class: "chart-empty", text: "Sem dados para os filtros atuais." }));
          return;
        }
        var max = Math.max.apply(null, data.map(function (d) { return d.value; })) || 1;
        data.forEach(function (d) {
          var pct = Math.max(3, Math.round((d.value / max) * 100));
          var row = el("div", { class: "bar-row" });
          row.appendChild(el("span", { class: "bl", text: d.label, title: d.label }));
          var track = el("div", { class: "bt" });
          track.appendChild(el("div", { class: "bf", style: "width:" + pct + "%; background:" + (d.color || "var(--accent)") + ";" }));
          row.appendChild(track);
          row.appendChild(el("span", { class: "bv", text: String(d.value) }));
          container.appendChild(row);
        });
      }

      function chartBox(title, data) {
        var box = el("div", { class: "chart-box" });
        box.appendChild(el("h3", { text: title }));
        var body = el("div");
        barList(body, data);
        box.appendChild(body);
        return box;
      }

      function statusPill(statusKey) {
        var m = STATUS_META[statusKey] || { label: statusKey, color: "var(--text-dim)", dim: "var(--off-dim)" };
        return el("span", { class: "pill", style: "background:" + m.dim + "; color:" + m.color + ";", text: m.label });
      }

      function renderLoss(loss) {
        return el("div", { class: "loss-row " + loss.severity }, [
          el("span", { class: "code", text: "[" + loss.severity.toUpperCase() + "] " + loss.code }),
          el("span", { text: loss.message + (loss.affected_value !== null && loss.affected_value !== undefined ? " (valor: " + loss.affected_value + ")" : "") })
        ]);
      }

      function renderCanonicalBlock(c) {
        if (!c) return el("div", { class: "empty-state", text: "Sem leitura da origem." });
        var wrap = el("div", { class: "canon-block" });
        function kv(label, valueNode) {
          var box = el("div", { class: "kv" });
          box.appendChild(el("span", { class: "k", text: label }));
          var v = el("span", { class: "v" });
          if (typeof valueNode === "string") v.textContent = valueNode; else v.appendChild(valueNode);
          box.appendChild(v);
          wrap.appendChild(box);
        }
        kv("Valor", (c.value === null ? "—" : String(c.value)) + (c.unit ? " " + c.unit : ""));
        kv("Tipo", c.data_type);
        kv("Qualidade", qualityInline(c.quality));
        kv("Timestamp", fmtIso(c.timestamp.value_utc) + " · " + c.timestamp.sync_source);
        return wrap;
      }

      function renderTargetCard(protocol, data) {
        if (data && data.error) {
          return el("div", { class: "target-card errored" }, [
            el("div", { class: "th" }, [el("span", { class: "proto", text: PROTO_LABEL[protocol] || protocol }), el("span", { class: "pill bad", text: "sem binding" })]),
            el("div", { text: data.error, style: "color:var(--bad); font-size:12.5px;" })
          ]);
        }
        var card = el("div", { class: "target-card" });
        var head = el("div", { class: "th" }, [el("span", { class: "proto", text: PROTO_LABEL[protocol] || protocol })]);
        if (data.status_code_severity) {
          var sevCls = data.status_code_severity === "Good" ? "good" : (data.status_code_severity === "Uncertain" ? "warn" : "bad");
          head.appendChild(el("span", { class: "pill " + sevCls, text: "StatusCode " + data.status_code_severity }));
        }
        card.appendChild(head);
        card.appendChild(el("div", { class: "addr", text: "endereço " + data.address }));
        card.appendChild(el("div", { class: "written", text: String(data.written_value) }));
        if (data.quality) card.appendChild(el("div", { style: "margin-bottom:6px;" }, [qualityInline(data.quality)]));
        if (data.timestamp) card.appendChild(el("div", { class: "hint-line", text: fmtIso(data.timestamp.value_utc) }));
        if (data.losses && data.losses.length) {
          data.losses.forEach(function (loss) { card.appendChild(renderLoss(loss)); });
        } else {
          card.appendChild(el("div", { class: "no-loss", text: "✓ nenhuma perda de metadados" }));
        }
        return card;
      }

      function renderReport(report) {
        var wrap = el("div");
        if (report.failure) {
          wrap.appendChild(el("div", { class: "failure-banner" }, [
            el("span", { html: "⚠" }),
            el("span", {}, [el("b", { text: "Falha na leitura da origem: " }), document.createTextNode(report.failure + ". O valor foi congelado no último bom conhecido.")])
          ]));
        }
        wrap.appendChild(renderCanonicalBlock(report.canonical));
        Object.keys(report.targets || {}).forEach(function (proto) {
          wrap.appendChild(renderTargetCard(proto, report.targets[proto]));
        });
        return wrap;
      }

      /* ============ PAINEL ============ */
      function initPainel() {
        loadAdapters();
        loadPointsQuick();
        activePolls.adapters = setInterval(loadAdapters, 5000);
      }

      function initDashboard() {
        loadDashboardSummary();
        activePolls.dashboard = setInterval(loadDashboardSummary, 5000);
      }

      function loadDashboardSummary() {
        Promise.all([
          apiGet("/api/mappings"),
          apiGet("/api/adapters"),
          apiGet("/api/logs?limit=300")
        ]).then(function (results) {
          var mappings = results[0], adaptersInfo = results[1], logs = results[2];

          var connectedCount = Object.keys(adaptersInfo).filter(function (k) { return adaptersInfo[k].connected; }).length;
          var openCircuits = Object.keys(adaptersInfo).filter(function (k) { return adaptersInfo[k].circuit_state === "open"; }).length;
          var conversionLogs = logs.filter(function (e) { return e.kind === "convert"; });
          var totalEvents = logs.length;
          var failedEvents = conversionLogs.filter(function (e) { return e.failure; }).length;
          var lossEvents = 0;
          var targetCount = 0;
          var preservedTargets = 0;
          var lossReasons = {};
          conversionLogs.forEach(function (entry) {
            Object.keys(entry.targets || {}).forEach(function (protocol) {
              var target = entry.targets[protocol];
              if (!target || target.error) return;
              targetCount += 1;
              if (target.losses && target.losses.length) {
                lossEvents += target.losses.length;
                target.losses.forEach(function (loss) {
                  lossReasons[loss.code] = (lossReasons[loss.code] || 0) + 1;
                });
              } else {
                preservedTargets += 1;
              }
            });
          });
          var lossConversionCount = conversionLogs.filter(function (e) {
            return Object.keys(e.targets || {}).some(function (p) {
              var target = e.targets[p];
              return target && target.losses && target.losses.length;
            });
          }).length;
          var cleanConversions = conversionLogs.length - failedEvents - lossConversionCount;

          var grid = document.getElementById("dash-stats-grid");
          grid.innerHTML = "";
          function stat(label, value, sub) {
            grid.appendChild(el("div", { class: "stat-card" }, [
              el("span", { class: "stat-label", text: label }),
              el("span", { class: "stat-value", text: String(value) }),
              sub ? el("span", { class: "stat-sub", text: sub }) : null
            ]));
          }
          stat("Pontos cadastrados", mappings.length);
          stat("Adaptadores conectados", connectedCount + "/4", openCircuits ? openCircuits + " circuito(s) aberto(s)" : "todos operando");
          stat("Eventos na sessão", totalEvents, failedEvents ? failedEvents + " com falha de comunicação" : "sem falhas registradas");
          stat("Conversões realizadas", conversionLogs.length, totalEvents ? Math.round((conversionLogs.length / totalEvents) * 100) + "% dos eventos" : "");
          stat("Metadados preservados", preservedTargets, targetCount ? Math.round((preservedTargets / targetCount) * 100) + "% dos destinos" : "sem destinos avaliados");
          stat("Perdas encontradas", lossEvents, lossConversionCount ? lossConversionCount + " conversão(ões) afetada(s)" : "nenhuma conversão afetada");
          stat("Conversões sem perda", cleanConversions, conversionLogs.length ? Math.round((cleanConversions / conversionLogs.length) * 100) + "% das conversões" : "sem conversões");

          var byProto = {};
          mappings.forEach(function (m) { m.protocols.forEach(function (p) { byProto[p] = (byProto[p] || 0) + 1; }); });
          var protoData = PROTOCOLS.filter(function (p) { return byProto[p.id]; })
            .map(function (p) { return { label: p.label, value: byProto[p.id], color: PROTO_COLOR[p.id] }; });
          barList(document.getElementById("dash-chart-protocols"), protoData);

          var byKind = {};
          logs.forEach(function (e) { byKind[e.kind] = (byKind[e.kind] || 0) + 1; });
          var kindData = Object.keys(byKind).map(function (k) { return { label: KIND_LABEL[k] || k, value: byKind[k], color: "var(--accent)" }; });
          barList(document.getElementById("dash-chart-eventkinds"), kindData);

          var reasonData = Object.keys(lossReasons).map(function (code) {
            return { label: code, value: lossReasons[code], color: "var(--warn)" };
          }).sort(function (a, b) { return b.value - a.value; });
          barList(document.getElementById("dash-chart-loss-reasons"), reasonData);
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar o resumo do painel."); });
      }

      function loadAdapters() {
        apiGet("/api/adapters").then(function (data) {
          var grid = document.getElementById("adapters-grid");
          grid.innerHTML = "";
          PROTOCOLS.forEach(function (p) {
            var info = data[p.id] || { connected: false, circuit_state: "closed" };
            var card = el("div", { class: "adapter-card" });
            var top = el("div", { class: "row-top" }, [
              el("div", {}, [
                el("div", { class: "proto-name", text: p.label }),
                el("div", { class: "proto-full", text: p.full })
              ])
            ]);
            var sw = el("label", { class: "switch", title: info.connected ? "Desligar comunicação" : "Ligar comunicação" });
            var input = el("input", { type: "checkbox" });
            input.checked = !!info.connected;
            input.addEventListener("change", function () {
              setAdapterConnection(p.id, input.checked);
            });
            sw.appendChild(input);
            sw.appendChild(el("span", { class: "track" }, [el("span", { class: "thumb" })]));
            top.appendChild(sw);
            card.appendChild(top);
            card.appendChild(el("div", { style: "display:flex; align-items:center; gap:8px;" }, [
              el("span", { class: "dot " + (info.connected ? "good" : "off") }),
              el("span", { style: "font-size:12px; color:var(--text-dim);", text: info.connected ? "conectado" : "desconectado" })
            ]));
            card.appendChild(circuitPill(info.circuit_state));
            grid.appendChild(card);
          });
          document.getElementById("adapters-updated").textContent = "atualizado às " + new Date().toLocaleTimeString("pt-BR", { hour12: false });
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar os adaptadores."); });
      }

      function setAdapterConnection(protocol, connected) {
        apiPost("/api/adapters/" + protocol + "/connection", { connected: connected }).then(function () {
          toast((connected ? "Adaptador '" + protocol + "' religado." : "Adaptador '" + protocol + "' desligado — comunicação indisponível."), connected ? "success" : "");
          loadAdapters();
        }).catch(function (err) { reportApiError(err, "Não foi possível alterar a conexão."); loadAdapters(); });
      }

      document.getElementById("btn-run-demo").addEventListener("click", function () {
        var btn = document.getElementById("btn-run-demo");
        btn.disabled = true;
        document.getElementById("demo-feedback").textContent = "rodando…";
        apiPost("/api/demo").then(function (entries) {
          document.getElementById("demo-feedback").textContent = entries.length + " evento(s) gerado(s) — veja em Histórico.";
          toast("Demonstração concluída: " + entries.length + " evento(s) registrado(s).", "success");
          loadAdapters();
          loadDashboardSummary();
        }).catch(function (err) {
          reportApiError(err, "Falha ao rodar a demonstração.");
          document.getElementById("demo-feedback").textContent = "";
        }).then(function () { btn.disabled = false; });
      });

      function loadPointsQuick() {
        apiGet("/api/mappings").then(function (list) {
          var grid = document.getElementById("points-quick-grid");
          grid.innerHTML = "";
          document.getElementById("points-count").textContent = "(" + list.length + ")";
          if (!list.length) {
            grid.appendChild(el("div", { class: "empty-state", text: "Nenhum ponto cadastrado ainda. Vá em Mapeamentos → Novo ponto." }));
            return;
          }
          list.forEach(function (m) {
            var card = el("button", {
              type: "button", class: "point-card", onclick: function () {
                conversorState.presetPoint = m.point_id;
                showView("conversor");
              }
            });
            card.appendChild(el("div", { class: "pid", text: m.point_id }));
            var row = el("div", { class: "protos" });
            m.protocols.forEach(function (p) { row.appendChild(protocolBadge(p)); });
            card.appendChild(row);
            grid.appendChild(card);
          });
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar os pontos."); });
      }

      /* ============ CONVERSOR ============ */
      var conversorState = { pointId: null, bindings: null, source: null, targets: {}, presetPoint: null };

      function initConversor() {
        var select = document.getElementById("conv-point-select");
        apiGet("/api/mappings").then(function (list) {
          select.innerHTML = "<option value=''>Selecione um ponto…</option>";
          list.forEach(function (m) {
            var opt = el("option", { value: m.point_id, text: m.point_id + "  (" + m.protocols.join(", ") + ")" });
            select.appendChild(opt);
          });
          if (conversorState.presetPoint) {
            select.value = conversorState.presetPoint;
            conversorState.presetPoint = null;
            onConvPointChange();
          }
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar os pontos."); });
      }

      document.getElementById("conv-point-select").addEventListener("change", onConvPointChange);

      function onConvPointChange() {
        var pointId = document.getElementById("conv-point-select").value;
        conversorState.pointId = pointId || null;
        conversorState.source = null;
        conversorState.targets = {};
        document.getElementById("conv-source-panel").style.display = "none";
        document.getElementById("conv-target-panel").style.display = "none";
        document.getElementById("conv-result").innerHTML = "";
        if (!pointId) return;
        apiGet("/api/mappings/" + encodeURIComponent(pointId)).then(function (detail) {
          conversorState.bindings = detail.bindings;
          renderSourceChips();
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar o ponto."); });
      }

      function renderSourceChips() {
        var wrap = document.getElementById("conv-source-chips");
        wrap.innerHTML = "";
        var available = Object.keys(conversorState.bindings);
        PROTOCOLS.forEach(function (p) {
          if (available.indexOf(p.id) === -1) return;
          var chip = el("button", { type: "button", class: "chip", text: p.label });
          chip.addEventListener("click", function () {
            conversorState.source = p.id;
            conversorState.targets = {};
            wrap.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("selected"); });
            chip.classList.add("selected");
            renderTargetChips();
          });
          wrap.appendChild(chip);
        });
        document.getElementById("conv-source-panel").style.display = "block";
        document.getElementById("conv-target-panel").style.display = "none";
        document.getElementById("conv-result").innerHTML = "";
      }

      function renderTargetChips() {
        var wrap = document.getElementById("conv-target-chips");
        wrap.innerHTML = "";
        PROTOCOLS.forEach(function (p) {
          if (p.id === conversorState.source) return;
          var hasBinding = !!conversorState.bindings[p.id];
          var chip = el("button", { type: "button", class: "chip" });
          chip.appendChild(document.createTextNode(p.label));
          if (!hasBinding) chip.appendChild(el("span", { class: "hint", text: "sem binding" }));
          chip.addEventListener("click", function () {
            conversorState.targets[p.id] = !conversorState.targets[p.id];
            chip.classList.toggle("selected", !!conversorState.targets[p.id]);
            updateConvertButton();
          });
          wrap.appendChild(chip);
        });
        document.getElementById("conv-target-panel").style.display = "block";
        document.getElementById("conv-result").innerHTML = "";
        updateConvertButton();
      }

      function updateConvertButton() {
        var anyTarget = Object.keys(conversorState.targets).some(function (k) { return conversorState.targets[k]; });
        document.getElementById("btn-convert").disabled = !anyTarget;
        document.getElementById("conv-hint").textContent = anyTarget ? "" : "escolha ao menos um destino";
      }

      document.getElementById("btn-convert").addEventListener("click", function () {
        var targets = Object.keys(conversorState.targets).filter(function (k) { return conversorState.targets[k]; });
        var btn = document.getElementById("btn-convert");
        btn.disabled = true;
        apiPost("/api/convert", { point_id: conversorState.pointId, source: conversorState.source, targets: targets })
          .then(function (report) {
            document.getElementById("conv-result").innerHTML = "";
            document.getElementById("conv-result").appendChild(renderReport(report));
          })
          .catch(function (err) { reportApiError(err, "Falha ao converter."); })
          .then(function () { btn.disabled = false; updateConvertButton(); });
      });

      /* ============ MAPEAMENTOS ============ */
      function initMapeamentos() {
        document.getElementById("mapping-detail-panel").style.display = "none";
        document.getElementById("mapping-form-panel").style.display = "none";
        loadMappingsTable();
      }

      function loadMappingsTable() {
        apiGet("/api/mappings").then(function (list) {
          var wrap = document.getElementById("mappings-table-wrap");
          wrap.innerHTML = "";
          if (!list.length) {
            wrap.appendChild(el("div", { class: "empty-state", text: "Nenhum ponto cadastrado. Use “Novo ponto” para começar." }));
            return;
          }
          var table = el("table", { class: "data" });
          table.appendChild(el("thead", {}, [el("tr", {}, [
            el("th", { text: "Ponto" }), el("th", { text: "Protocolos" }), el("th", { text: "" })
          ])]));
          var tbody = el("tbody");
          list.forEach(function (m) {
            var tr = el("tr", { class: "clickable" });
            tr.appendChild(el("td", { class: "pid", text: m.point_id }));
            var protoCell = el("td");
            m.protocols.forEach(function (p) { protoCell.appendChild(protocolBadge(p)); protoCell.appendChild(document.createTextNode(" ")); });
            tr.appendChild(protoCell);
            tr.appendChild(el("td", {}, [el("button", { class: "btn btn-sm", text: "ver", onclick: function (ev) { ev.stopPropagation(); showMappingDetail(m.point_id); } })]));
            tr.addEventListener("click", function () { showMappingDetail(m.point_id); });
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          wrap.appendChild(table);
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar os mapeamentos."); });
      }

      document.getElementById("btn-validate-all").addEventListener("click", function () {
        apiPost("/api/mappings/validate").then(function (results) {
          var ok = Object.keys(results).filter(function (k) { return results[k] === null; }).length;
          var total = Object.keys(results).length;
          var failed = Object.keys(results).filter(function (k) { return results[k] !== null; });
          if (failed.length) {
            toast(ok + "/" + total + " válidos. Falhas: " + failed.map(function (k) { return k + " — " + results[k]; }).join(" | "), "error");
          } else {
            toast("Todos os " + total + " ponto(s) são válidos.", "success");
          }
        }).catch(function (err) { reportApiError(err, "Falha ao validar."); });
      });

      function showMappingDetail(pointId) {
        document.getElementById("mapping-form-panel").style.display = "none";
        var panel = document.getElementById("mapping-detail-panel");
        panel.style.display = "block";
        panel.innerHTML = "<h2>Carregando…</h2>";
        apiGet("/api/mappings/" + encodeURIComponent(pointId)).then(function (detail) {
          panel.innerHTML = "";
          var head = el("h2", {}, [
            el("span", { class: "mono", text: detail.point_id }),
            el("span", { style: "display:flex; gap:8px;" }, [
              el("button", { class: "btn btn-sm", text: "Validar", onclick: function () { validateOne(pointId); } }),
              el("button", { class: "btn btn-sm btn-danger", text: "Excluir", onclick: function () { deleteMapping(pointId); } }),
              el("button", { class: "btn btn-sm btn-ghost", text: "Fechar", onclick: function () { panel.style.display = "none"; } })
            ])
          ]);
          panel.appendChild(head);
          panel.appendChild(el("div", { id: "mapping-validate-result" }));

          var table = el("table", { class: "data" });
          table.appendChild(el("thead", {}, [el("tr", {}, [
            "Protocolo", "Endereço", "Tipo", "Unidade", "Escala", "Offset", "Validade nativa", "Flags nativas", "Faixa"
          ].map(function (t) { return el("th", { text: t }); }))]));
          var tbody = el("tbody");
          Object.keys(detail.bindings).forEach(function (proto) {
            var b = detail.bindings[proto];
            tbody.appendChild(el("tr", {}, [
              el("td", {}, [protocolBadge(proto)]),
              el("td", { class: "mono", text: b.address }),
              el("td", { text: b.data_type }),
              el("td", { text: b.unit || "—" }),
              el("td", { text: String(b.scale) }),
              el("td", { text: String(b.offset) }),
              el("td", { text: b.native_validity || "—" }),
              el("td", { text: (b.native_quality_flags && b.native_quality_flags.length) ? b.native_quality_flags.join(", ") : "—" }),
              el("td", { text: (b.min_engineering === null && b.max_engineering === null) ? "—" : ((b.min_engineering !== null ? b.min_engineering : "−∞") + " … " + (b.max_engineering !== null ? b.max_engineering : "+∞")) })
            ]));
          });
          table.appendChild(tbody);
          panel.appendChild(table);
          panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar o ponto."); panel.style.display = "none"; });
      }

      function validateOne(pointId) {
        apiPost("/api/mappings/validate?point_id=" + encodeURIComponent(pointId)).then(function (res) {
          var msg = res[pointId];
          var box = document.getElementById("mapping-validate-result");
          if (box) box.innerHTML = "";
          if (msg) {
            toast(pointId + ": " + msg, "error");
            if (box) box.appendChild(el("div", { class: "field-error", text: msg }));
          } else {
            toast(pointId + ": mapeamento válido.", "success");
          }
        }).catch(function (err) { reportApiError(err, "Falha ao validar."); });
      }

      function deleteMapping(pointId) {
        if (!confirm("Excluir o ponto '" + pointId + "'? Essa ação não pode ser desfeita.")) return;
        apiDelete("/api/mappings/" + encodeURIComponent(pointId)).then(function () {
          toast("Ponto '" + pointId + "' removido.", "success");
          document.getElementById("mapping-detail-panel").style.display = "none";
          loadMappingsTable();
        }).catch(function (err) { reportApiError(err, "Falha ao excluir."); });
      }

      /* ---- new mapping form ---- */
      var formBindingCount = 0;

      document.getElementById("btn-new-mapping").addEventListener("click", function () {
        document.getElementById("mapping-detail-panel").style.display = "none";
        openMappingForm();
      });

      function openMappingForm() {
        var panel = document.getElementById("mapping-form-panel");
        panel.style.display = "block";
        panel.innerHTML = "";
        panel.appendChild(el("h2", {}, [
          el("span", { text: "Novo ponto" }),
          el("button", { class: "btn btn-sm btn-ghost", text: "Fechar", onclick: function () { panel.style.display = "none"; } })
        ]));

        var form = el("form");
        var pointIdField = el("label", { class: "field", style: "max-width:340px; margin-bottom:14px;" }, [
          el("span", { class: "lbl", text: "Identificador do ponto (point_id)" }),
          el("input", { type: "text", id: "f-point-id", placeholder: "ex: SE02.MMXU2.PhV.phsB", required: "required" })
        ]);
        form.appendChild(pointIdField);

        var bindingsWrap = el("div", { id: "f-bindings-wrap" });
        form.appendChild(bindingsWrap);

        formBindingCount = 0;
        addBindingBlock(bindingsWrap);
        addBindingBlock(bindingsWrap);

        var addBtn = el("button", { type: "button", class: "btn btn-sm", text: "+ adicionar protocolo" });
        addBtn.addEventListener("click", function () { addBindingBlock(bindingsWrap); });
        form.appendChild(addBtn);

        form.appendChild(el("div", { id: "f-error" }));

        var actions = el("div", { style: "margin-top:16px; display:flex; gap:10px;" }, [
          el("button", { type: "submit", class: "btn btn-primary", text: "Cadastrar ponto" })
        ]);
        form.appendChild(actions);

        form.addEventListener("submit", function (ev) {
          ev.preventDefault();
          submitMappingForm(bindingsWrap);
        });

        panel.appendChild(form);
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      function addBindingBlock(wrap) {
        formBindingCount += 1;
        var idx = formBindingCount;
        var block = el("fieldset", { class: "binding-block", "data-idx": idx });
        block.appendChild(el("legend", { text: "binding #" + idx }));

        var grid = el("div", { class: "grid cols-3" });

        var protoSelect = el("select", { class: "f-protocol" });
        PROTOCOLS.forEach(function (p) { protoSelect.appendChild(el("option", { value: p.id, text: p.full })); });
        protoSelect.selectedIndex = (idx - 1) % PROTOCOLS.length;
        grid.appendChild(fieldWrap("Protocolo", protoSelect));

        var addrInput = el("input", { type: "text", class: "f-address", placeholder: "ex: 40010 / ns=2;s=Point / BI12" });
        grid.appendChild(fieldWrap("Endereço", addrInput));

        var typeSelect = el("select", { class: "f-datatype" });
        DATA_TYPES.forEach(function (t) { typeSelect.appendChild(el("option", { value: t, text: t })); });
        grid.appendChild(fieldWrap("Tipo de dado", typeSelect));

        var unitSelect = el("select", { class: "f-unit" });
        KNOWN_UNITS.forEach(function (u) { unitSelect.appendChild(el("option", { value: u.v, text: u.label })); });
        grid.appendChild(fieldWrap("Unidade", unitSelect));

        var scaleInput = el("input", { type: "number", step: "any", class: "f-scale", value: "1" });
        grid.appendChild(fieldWrap("Escala", scaleInput));

        var offsetInput = el("input", { type: "number", step: "any", class: "f-offset", value: "0" });
        grid.appendChild(fieldWrap("Offset", offsetInput));

        var rawInput = el("input", { type: "text", class: "f-raw", placeholder: "ex: 13.8 / true / 100" });
        grid.appendChild(fieldWrap("Valor bruto inicial (raw_value)", rawInput));

        var validitySelect = el("select", { class: "f-validity" });
        VALIDITY_OPTIONS.forEach(function (v) { validitySelect.appendChild(el("option", { value: v.v, text: v.label })); });
        grid.appendChild(fieldWrap("Validade nativa", validitySelect));

        var minInput = el("input", { type: "number", step: "any", class: "f-min", placeholder: "sem mínimo" });
        grid.appendChild(fieldWrap("Mínimo de engenharia", minInput));

        var maxInput = el("input", { type: "number", step: "any", class: "f-max", placeholder: "sem máximo" });
        grid.appendChild(fieldWrap("Máximo de engenharia", maxInput));

        block.appendChild(grid);

        var flagsWrap = el("div", { style: "margin-top:12px;" }, [el("span", { class: "lbl", style: "font-size:12.5px; color:var(--text-dim); display:block; margin-bottom:6px;", text: "Flags de qualidade nativas" })]);
        var flagsRow = el("div", { style: "display:flex; gap:14px; flex-wrap:wrap;" });
        QUALITY_FLAGS.forEach(function (f) {
          var line = el("label", { class: "checkline" }, [
            el("input", { type: "checkbox", class: "f-flag", value: f }),
            el("span", { text: f })
          ]);
          flagsRow.appendChild(line);
        });
        flagsWrap.appendChild(flagsRow);
        block.appendChild(flagsWrap);

        if (formBindingCount > 0) {
          var removeBtn = el("button", { type: "button", class: "btn btn-sm btn-ghost", style: "margin-top:12px;", text: "remover este protocolo" });
          removeBtn.addEventListener("click", function () { block.remove(); });
          block.appendChild(removeBtn);
        }

        wrap.appendChild(block);
      }

      function fieldWrap(label, inputNode) {
        return el("label", { class: "field" }, [el("span", { class: "lbl", text: label }), inputNode]);
      }

      function parseRaw(text, dataType) {
        if (text === "" || text === undefined || text === null) return null;
        if (dataType === "bool") return /^(true|1|sim)$/i.test(text.trim());
        if (dataType === "int") { var i = parseInt(text, 10); return isNaN(i) ? text : i; }
        if (dataType === "float") { var f = parseFloat(text); return isNaN(f) ? text : f; }
        var n = Number(text);
        return isNaN(n) ? text : n;
      }

      function submitMappingForm(wrap) {
        var errorBox = document.getElementById("f-error");
        errorBox.innerHTML = "";
        var pointId = document.getElementById("f-point-id").value.trim();
        if (!pointId) {
          errorBox.appendChild(el("div", { class: "field-error", text: "Informe o identificador do ponto." }));
          return;
        }
        var blocks = wrap.querySelectorAll(".binding-block");
        if (blocks.length < 2) {
          errorBox.appendChild(el("div", { class: "field-error", text: "O gateway exige ao menos 2 protocolos por ponto." }));
          return;
        }
        var bindings = {};
        var protoUsed = {};
        var dup = false;
        blocks.forEach(function (block) {
          var proto = block.querySelector(".f-protocol").value;
          if (protoUsed[proto]) dup = true;
          protoUsed[proto] = true;
          var dataType = block.querySelector(".f-datatype").value;
          var flags = Array.prototype.slice.call(block.querySelectorAll(".f-flag:checked")).map(function (i) { return i.value; });
          var minVal = block.querySelector(".f-min").value;
          var maxVal = block.querySelector(".f-max").value;
          var validity = block.querySelector(".f-validity").value;
          bindings[proto] = {
            protocol: proto,
            address: block.querySelector(".f-address").value.trim(),
            data_type: dataType,
            unit: block.querySelector(".f-unit").value,
            scale: parseFloat(block.querySelector(".f-scale").value || "1"),
            offset: parseFloat(block.querySelector(".f-offset").value || "0"),
            raw_value: parseRaw(block.querySelector(".f-raw").value.trim(), dataType),
            native_validity: validity || null,
            native_quality_flags: flags,
            min_engineering: minVal === "" ? null : parseFloat(minVal),
            max_engineering: maxVal === "" ? null : parseFloat(maxVal)
          };
        });
        if (dup) {
          errorBox.appendChild(el("div", { class: "field-error", text: "Você selecionou o mesmo protocolo mais de uma vez." }));
          return;
        }
        apiPost("/api/mappings", { point_id: pointId, bindings: bindings }).then(function () {
          toast("Ponto '" + pointId + "' cadastrado.", "success");
          document.getElementById("mapping-form-panel").style.display = "none";
          loadMappingsTable();
        }).catch(function (err) {
          errorBox.appendChild(el("div", { class: "field-error", text: err.message }));
        });
      }

      /* ============ HISTÓRICO ============ */
      var lastLogId = 0;
      var logsAccum = [];
      var openLogIds = {};
      var historicoInited = false;
      var historicoState = {
        search: "",
        protocols: {},   // proto id -> true when selected as filter
        statuses: {},    // status key -> true when selected as filter
        sort: "time_desc",
        group: "none",
        view: "lista"
      };

      function entryProtocols(entry) {
        var set = {};
        if (entry.source_protocol) set[entry.source_protocol] = true;
        Object.keys(entry.targets || {}).forEach(function (p) { set[p] = true; });
        var keys = Object.keys(set);
        return keys.length ? keys : ["sistema"];
      }

      function entryLossCount(entry) {
        var n = 0;
        Object.keys(entry.targets || {}).forEach(function (p) {
          var t = entry.targets[p];
          if (t && t.losses) n += t.losses.length;
        });
        return n;
      }

      function entryLabel(entry) {
        return entry.kind === "convert" ? entry.point_id : (entry.message || entry.kind);
      }

      function classifyEntry(entry) {
        if (entry.kind === "error") return "erro";
        if (entry.kind === "info") return "info";
        if (entry.failure) return "falha_comm";
        return entryLossCount(entry) > 0 ? "perda" : "ok";
      }

      function initHistorico() {
        logsAccum = []; lastLogId = 0;
        if (!historicoInited) bindHistoricoToolbar();
        loadLogs();
        activePolls.logs = setInterval(loadLogs, 4000);
      }

      function bindHistoricoToolbar() {
        historicoInited = true;

        var protocolOptions = PROTOCOLS.map(function (p) { return { id: p.id, label: p.label }; })
          .concat([{ id: "sistema", label: "Sistema" }]);
        renderFilterChips(document.getElementById("hist-filter-protocol"), protocolOptions, historicoState.protocols, function () { renderHistorico(); });

        var statusOptions = Object.keys(STATUS_META).map(function (k) { return { id: k, label: STATUS_META[k].label }; });
        renderFilterChips(document.getElementById("hist-filter-status"), statusOptions, historicoState.statuses, function () { renderHistorico(); });

        document.getElementById("hist-search").addEventListener("input", function (ev) {
          historicoState.search = ev.target.value;
          renderHistorico();
        });
        document.getElementById("hist-sort").addEventListener("change", function (ev) {
          historicoState.sort = ev.target.value;
          renderHistorico();
        });
        document.getElementById("hist-group").addEventListener("change", function (ev) {
          historicoState.group = ev.target.value;
          renderHistorico();
        });
        document.querySelectorAll("#hist-view-switch .subtab").forEach(function (btn) {
          btn.addEventListener("click", function () { setHistView(btn.dataset.hview); });
        });
      }

      function renderFilterChips(container, options, selectedMap, onChange) {
        container.innerHTML = "";
        options.forEach(function (opt) {
          var chip = el("button", { type: "button", class: "chip" + (selectedMap[opt.id] ? " selected" : ""), text: opt.label });
          chip.addEventListener("click", function () {
            selectedMap[opt.id] = !selectedMap[opt.id];
            chip.classList.toggle("selected", !!selectedMap[opt.id]);
            onChange();
          });
          container.appendChild(chip);
        });
      }

      function setHistView(name) {
        historicoState.view = name;
        document.querySelectorAll("#hist-view-switch .subtab").forEach(function (b) {
          b.classList.toggle("active", b.dataset.hview === name);
        });
        ["lista", "tabela", "graficos"].forEach(function (v) {
          document.getElementById("hist-view-" + v).style.display = (v === name) ? "block" : "none";
        });
      }

      function loadLogs() {
        apiGet("/api/logs?limit=100&since_id=" + lastLogId).then(function (entries) {
          if (entries.length) {
            logsAccum = logsAccum.concat(entries);
            lastLogId = entries[entries.length - 1].id;
          }
          renderHistorico();
        }).catch(function (err) { reportApiError(err, "Não foi possível carregar o histórico."); });
      }

      function historicoFiltered() {
        var q = historicoState.search.trim().toLowerCase();
        var protoKeys = Object.keys(historicoState.protocols).filter(function (k) { return historicoState.protocols[k]; });
        var statusKeys = Object.keys(historicoState.statuses).filter(function (k) { return historicoState.statuses[k]; });
        return logsAccum.filter(function (entry) {
          if (protoKeys.length) {
            var eProtos = entryProtocols(entry);
            if (!eProtos.some(function (p) { return protoKeys.indexOf(p) !== -1; })) return false;
          }
          if (statusKeys.length && statusKeys.indexOf(classifyEntry(entry)) === -1) return false;
          if (q) {
            var hay = [entryLabel(entry), entry.source_protocol || "", entry.message || "", Object.keys(entry.targets || {}).join(" ")]
              .join(" ").toLowerCase();
            if (hay.indexOf(q) === -1) return false;
          }
          return true;
        });
      }

      function historicoSort(list) {
        var arr = list.slice();
        var s = historicoState.sort;
        arr.sort(function (a, b) {
          if (s === "time_asc") return a.logged_at - b.logged_at || a.id - b.id;
          if (s === "point_asc") return entryLabel(a).localeCompare(entryLabel(b));
          if (s === "point_desc") return entryLabel(b).localeCompare(entryLabel(a));
          if (s === "protocol_asc") return (a.source_protocol || "").localeCompare(b.source_protocol || "");
          if (s === "losses_desc") return entryLossCount(b) - entryLossCount(a) || b.logged_at - a.logged_at;
          return b.logged_at - a.logged_at || b.id - a.id; // time_desc (default)
        });
        return arr;
      }

      function historicoGroup(list) {
        var g = historicoState.group;
        if (g === "none") return [{ key: "all", label: null, items: list }];
        var map = {}, order = [];
        list.forEach(function (entry) {
          var key, label;
          if (g === "point") { key = entry.kind === "convert" ? entry.point_id : "(sistema)"; label = key; }
          else if (g === "protocol") { key = entry.source_protocol || "sistema"; label = PROTO_LABEL[key] || "Sistema"; }
          else if (g === "status") { key = classifyEntry(entry); label = STATUS_META[key].label; }
          else { key = entry.kind; label = KIND_LABEL[key] || key; }
          if (!map[key]) { map[key] = { key: key, label: label, items: [] }; order.push(key); }
          map[key].items.push(entry);
        });
        return order.map(function (k) { return map[k]; });
      }

      function buildLogItem(entry) {
        var item = el("div", { class: "log-item kind-" + entry.kind });
        var isConvert = entry.kind === "convert";
        var head = el("div", { class: "log-head" }, [
          el("span", { class: "dot " + (entry.kind === "error" ? "bad" : (entry.failure ? "warn" : (isConvert && entryLossCount(entry) ? "warn" : "good"))) }),
          el("span", { class: "pid", text: entryLabel(entry) }),
          el("span", { class: "ts", text: fmtTime(entry.logged_at) })
        ]);
        if (isConvert) {
          head.appendChild(statusPill(classifyEntry(entry)));
          head.appendChild(el("span", { class: "hint-line", text: "#" + entry.id + " · " + entry.source_protocol + " →" }));
          head.addEventListener("click", function () {
            openLogIds[entry.id] = !openLogIds[entry.id];
            renderHistorico();
          });
        }
        item.appendChild(head);
        if (isConvert) {
          var body = el("div", { class: "log-body" + (openLogIds[entry.id] ? " open" : "") });
          if (openLogIds[entry.id]) body.appendChild(renderReport(entry));
          item.appendChild(body);
        }
        return item;
      }

      function renderHistLista(groups, total) {
        var wrap = document.getElementById("hist-view-lista");
        wrap.innerHTML = "";
        if (!total) {
          wrap.appendChild(el("div", { class: "empty-state", text: logsAccum.length ? "Nenhum evento corresponde aos filtros atuais." : "Nenhum evento ainda. Rode a demonstração no Painel ou faça uma conversão." }));
          return;
        }
        groups.forEach(function (g) {
          if (g.label !== null) {
            wrap.appendChild(el("div", { class: "group-header" }, [
              el("span", { text: g.label }), el("span", { class: "gcount", text: g.items.length + " evento(s)" })
            ]));
          }
          g.items.forEach(function (entry) { wrap.appendChild(buildLogItem(entry)); });
        });
      }

      function sortableTh(label, sortKey) {
        var isSorted = historicoState.sort === sortKey;
        var node = el("th", { class: "sortable" + (isSorted ? " sorted" : "") }, [
          document.createTextNode(label),
          el("span", { class: "arrow", text: isSorted ? (historicoState.sort.indexOf("desc") !== -1 ? "↓" : "↑") : "↕" })
        ]);
        node.addEventListener("click", function () {
          historicoState.sort = sortKey;
          document.getElementById("hist-sort").value = sortKey;
          renderHistorico();
        });
        return node;
      }

      function renderHistTabela(groups, total) {
        var wrap = document.getElementById("hist-view-tabela");
        wrap.innerHTML = "";
        if (!total) {
          wrap.appendChild(el("div", { class: "empty-state", text: logsAccum.length ? "Nenhum evento corresponde aos filtros atuais." : "Nenhum evento ainda." }));
          return;
        }
        groups.forEach(function (g) {
          if (g.label !== null) {
            wrap.appendChild(el("div", { class: "group-header" }, [
              el("span", { text: g.label }), el("span", { class: "gcount", text: g.items.length + " evento(s)" })
            ]));
          }
          var table = el("table", { class: "data" });
          table.appendChild(el("thead", {}, [el("tr", {}, [
            el("th", { text: "#" }), sortableTh("Horário", "time_desc"), el("th", { text: "Tipo" }),
            sortableTh("Ponto / mensagem", "point_asc"), sortableTh("Origem", "protocol_asc"),
            el("th", { text: "Destinos" }), el("th", { text: "Status" }), sortableTh("Perdas", "losses_desc")
          ])]));
          var tbody = el("tbody");
          g.items.forEach(function (entry) {
            var isConvert = entry.kind === "convert";
            var tr = el("tr", { class: isConvert ? "clickable" : "" });
            if (isConvert) {
              tr.addEventListener("click", function () {
                openLogIds[entry.id] = true;
                setHistView("lista");
                renderHistorico();
              });
            }
            var targetsCell = el("td");
            Object.keys(entry.targets || {}).forEach(function (p) { targetsCell.appendChild(protocolBadge(p)); targetsCell.appendChild(document.createTextNode(" ")); });
            tr.appendChild(el("td", { class: "mono", text: "#" + entry.id }));
            tr.appendChild(el("td", { class: "mono", text: fmtTime(entry.logged_at) }));
            tr.appendChild(el("td", { text: KIND_LABEL[entry.kind] || entry.kind }));
            tr.appendChild(el("td", { class: "mono", text: entryLabel(entry) }));
            tr.appendChild(el("td", {}, entry.source_protocol ? [protocolBadge(entry.source_protocol)] : [document.createTextNode("—")]));
            tr.appendChild(targetsCell.childNodes.length ? targetsCell : el("td", { text: "—" }));
            tr.appendChild(el("td", {}, [statusPill(classifyEntry(entry))]));
            tr.appendChild(el("td", { class: "mono", text: String(entryLossCount(entry)) }));
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          wrap.appendChild(table);
        });
      }

      function renderHistGraficos(list) {
        var wrap = document.getElementById("hist-view-graficos");
        wrap.innerHTML = "";
        if (!list.length) {
          wrap.appendChild(el("div", { class: "empty-state", text: logsAccum.length ? "Nenhum evento corresponde aos filtros atuais." : "Nenhum evento ainda." }));
          return;
        }
        var grid = el("div", { class: "grid cols-2" });

        var byProto = {};
        list.forEach(function (e) { if (e.source_protocol) byProto[e.source_protocol] = (byProto[e.source_protocol] || 0) + 1; });
        var protoData = PROTOCOLS.filter(function (p) { return byProto[p.id]; })
          .map(function (p) { return { label: p.label, value: byProto[p.id], color: PROTO_COLOR[p.id] }; });
        grid.appendChild(chartBox("Conversões por protocolo de origem", protoData));

        var byStatus = {};
        list.forEach(function (e) { var s = classifyEntry(e); byStatus[s] = (byStatus[s] || 0) + 1; });
        var statusData = Object.keys(STATUS_META).filter(function (k) { return byStatus[k]; })
          .map(function (k) { return { label: STATUS_META[k].label, value: byStatus[k], color: STATUS_META[k].color }; });
        grid.appendChild(chartBox("Eventos por status", statusData));

        var byKind = {};
        list.forEach(function (e) { byKind[e.kind] = (byKind[e.kind] || 0) + 1; });
        var kindData = Object.keys(byKind).map(function (k) { return { label: KIND_LABEL[k] || k, value: byKind[k], color: "var(--accent)" }; });
        grid.appendChild(chartBox("Eventos por tipo", kindData));

        var bySeverity = {};
        list.forEach(function (e) {
          Object.keys(e.targets || {}).forEach(function (p) {
            var t = e.targets[p];
            (t && t.losses ? t.losses : []).forEach(function (l) { bySeverity[l.severity] = (bySeverity[l.severity] || 0) + 1; });
          });
        });
        var sevColor = { error: "var(--bad)", warning: "var(--warn)", info: "var(--info)" };
        var sevData = Object.keys(bySeverity).map(function (k) { return { label: k, value: bySeverity[k], color: sevColor[k] || "var(--accent)" }; });
        grid.appendChild(chartBox("Perdas de metadados por severidade", sevData));

        var byPoint = {};
        list.forEach(function (e) { if (e.kind === "convert") byPoint[e.point_id] = (byPoint[e.point_id] || 0) + 1; });
        var pointData = Object.keys(byPoint).map(function (k) { return { label: k, value: byPoint[k], color: "var(--accent)" }; })
          .sort(function (a, b) { return b.value - a.value; }).slice(0, 8);
        grid.appendChild(chartBox("Pontos mais convertidos", pointData));

        var sortedByTime = list.slice().sort(function (a, b) { return a.logged_at - b.logged_at; });
        var bucketOrder = [], bucketMap = {};
        sortedByTime.forEach(function (e) {
          var d = new Date(e.logged_at * 1000);
          var key = String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
          if (!bucketMap[key]) { bucketMap[key] = 0; bucketOrder.push(key); }
          bucketMap[key] += 1;
        });
        var timelineData = bucketOrder.slice(-10).map(function (k) { return { label: k, value: bucketMap[k], color: "var(--accent)" }; });
        grid.appendChild(chartBox("Volume de eventos por minuto (janela recente)", timelineData));

        wrap.appendChild(grid);
      }

      function renderHistorico() {
        var filtered = historicoFiltered();
        var countEl = document.getElementById("hist-filter-count");
        if (countEl) countEl.textContent = "(" + filtered.length + " de " + logsAccum.length + ")";
        var sorted = historicoSort(filtered);
        var groups = historicoGroup(sorted);
        renderHistLista(groups, sorted.length);
        renderHistTabela(groups, sorted.length);
        renderHistGraficos(sorted);
      }

      document.getElementById("btn-refresh-logs").addEventListener("click", function () {
        lastLogId = 0; logsAccum = []; loadLogs();
      });

      document.getElementById("btn-clear-logs").addEventListener("click", function () {
        if (!confirm("Limpar todo o histórico de eventos?")) return;
        apiDelete("/api/logs").then(function () {
          logsAccum = []; lastLogId = 0; openLogIds = {};
          renderHistorico();
          toast("Histórico limpo.", "success");
        }).catch(function (err) { reportApiError(err, "Falha ao limpar histórico."); });
      });

      /* ============ help modal ============ */
      var helpBackdrop = document.getElementById("help-backdrop");
      document.getElementById("btn-help").addEventListener("click", function () { helpBackdrop.classList.add("open"); });
      document.getElementById("btn-help-close").addEventListener("click", function () { helpBackdrop.classList.remove("open"); });
      helpBackdrop.addEventListener("click", function (ev) { if (ev.target === helpBackdrop) helpBackdrop.classList.remove("open"); });
      document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") helpBackdrop.classList.remove("open"); });

      /* ============ boot ============ */
      var startView = (location.hash || "").replace("#", "");
      if (["painel", "conversor", "mapeamentos", "historico"].indexOf(startView) === -1) startView = "painel";
      showView(startView);

    })();
