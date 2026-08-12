const MAX_FILE_SIZE = 10 * 1024 * 1024;
const MAX_FILES = 50;

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const fileListSection = document.getElementById("fileListSection");
const fileList = document.getElementById("fileList");
const fileCount = document.getElementById("fileCount");
const extractBtn = document.getElementById("extractBtn");
const clearBtn = document.getElementById("clearBtn");
const statusSection = document.getElementById("statusSection");
const statusText = document.getElementById("statusText");
const errorSection = document.getElementById("errorSection");
const errorList = document.getElementById("errorList");
const resultSection = document.getElementById("resultSection");
const rowCount = document.getElementById("rowCount");
const resultTable = document.getElementById("resultTable");
const downloadBtn = document.getElementById("downloadBtn");
const addRowBtn = document.getElementById("addRowBtn");
const resetResultsBtn = document.getElementById("resetResultsBtn");

let selectedFiles = [];
let lastResultRows = [];
let lastColumns = [];

const updatePostalBtn = document.getElementById("updatePostalBtn");

updatePostalBtn.addEventListener("click", async () => {
  if (!lastResultRows.length) return;

  updatePostalBtn.disabled = true;
  updatePostalBtn.textContent = "업데이트 중...";

  try {
    const res = await fetch("/api/postal-codes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: lastResultRows }),
    });

    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "우편번호 업데이트 중 오류가 발생했습니다.");
      return;
    }

    lastResultRows = data.rows || lastResultRows;
    renderResultTable(lastColumns, lastResultRows);
  } catch (err) {
    alert("서버와 통신 중 오류가 발생했습니다: " + err.message);
  } finally {
    updatePostalBtn.disabled = false;
    updatePostalBtn.textContent = "우편번호 업데이트";
  }
});

function formatSize(bytes) {
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function renderFileList() {
  fileList.innerHTML = "";
  fileCount.textContent = selectedFiles.length;
  fileListSection.classList.toggle("hidden", selectedFiles.length === 0);

  selectedFiles.forEach((file, idx) => {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = file.name;
    const sizeSpan = document.createElement("span");
    sizeSpan.className = "file-size";
    sizeSpan.textContent = formatSize(file.size);
    label.appendChild(sizeSpan);

    const removeBtn = document.createElement("button");
    removeBtn.className = "file-remove";
    removeBtn.textContent = "삭제";
    removeBtn.addEventListener("click", () => {
      selectedFiles.splice(idx, 1);
      renderFileList();
    });

    li.appendChild(label);
    li.appendChild(removeBtn);
    fileList.appendChild(li);
  });
}

function addFiles(newFiles) {
  const incoming = Array.from(newFiles);
  const rejected = [];

  for (const file of incoming) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      rejected.push(`${file.name} (PDF 파일이 아닙니다)`);
      continue;
    }
    if (file.size > MAX_FILE_SIZE) {
      rejected.push(`${file.name} (10MB 초과)`);
      continue;
    }
    if (selectedFiles.length >= MAX_FILES) {
      rejected.push(`${file.name} (최대 ${MAX_FILES}개 제한 초과)`);
      continue;
    }
    selectedFiles.push(file);
  }

  if (rejected.length) {
    alert("다음 파일은 추가되지 않았습니다:\n" + rejected.join("\n"));
  }

  renderFileList();
}

dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", (e) => {
  addFiles(e.target.files);
  fileInput.value = "";
});

["dragenter", "dragover"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  addFiles(e.dataTransfer.files);
});

clearBtn.addEventListener("click", () => {
  selectedFiles = [];
  renderFileList();
});

const UNIT_FIELDS = [
  "해당번지",
  "주택명",
  "동명",
  "호수",
  "지번면적",
  "소유 토지면적",
  "건축물용도",
  "건축물소유연면적",
];
const READONLY_FIELDS = ["호수연번", "토지등소유자번호"];

function applyGrouping(rows) {
  let unitSeq = 0;
  let i = 0;
  while (i < rows.length) {
    const group = rows[i]._group;
    const groupRows = [rows[i]];
    let j = i + 1;
    if (group !== undefined && group !== null) {
      while (j < rows.length && rows[j]._group === group) {
        groupRows.push(rows[j]);
        j++;
      }
    }
    unitSeq++;
    groupRows.forEach((row, idx) => {
      const isFirst = idx === 0;
      row["호수연번"] = isFirst ? String(unitSeq) : "";
      row["토지등소유자번호"] = isFirst ? String(unitSeq) : `${unitSeq}-${idx}`;
      if (groupRows.length <= 1) {
        row["공동지분"] = "";
      }
      if (!isFirst) {
        UNIT_FIELDS.forEach((f) => {
          row[f] = "";
        });
      }
    });
    i = j;
  }
}

function renderResultTable(columns, rows) {
  applyGrouping(rows);

  const thead = resultTable.querySelector("thead");
  const tbody = resultTable.querySelector("tbody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  const headRow = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headRow.appendChild(th);
  });
  const deleteTh = document.createElement("th");
  headRow.appendChild(deleteTh);
  thead.appendChild(headRow);

  rows.forEach((row, rowIndex) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      td.textContent = row[col] || "";
      if (!READONLY_FIELDS.includes(col)) {
        td.classList.add("editable-cell");
        td.contentEditable = "true";
        td.dataset.col = col;
        td.addEventListener("input", () => {
          lastResultRows[rowIndex][col] = td.textContent.trim();
        });
      }
      tr.appendChild(td);
    });

    const deleteTd = document.createElement("td");
    deleteTd.className = "row-delete-cell";
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "row-delete-btn";
    deleteBtn.type = "button";
    deleteBtn.textContent = "삭제";
    deleteBtn.addEventListener("click", () => {
      lastResultRows.splice(rowIndex, 1);
      renderResultTable(lastColumns, lastResultRows);
    });
    deleteTd.appendChild(deleteBtn);
    tr.appendChild(deleteTd);

    tbody.appendChild(tr);
  });

  rowCount.textContent = rows.length;
}

addRowBtn.addEventListener("click", () => {
  const emptyRow = {};
  lastColumns.forEach((col) => {
    emptyRow[col] = "";
  });
  lastResultRows.push(emptyRow);
  renderResultTable(lastColumns, lastResultRows);
});

resetResultsBtn.addEventListener("click", () => {
  if (!lastResultRows.length) return;
  if (!confirm("추출 결과를 모두 초기화할까요? 다운로드하지 않은 내용은 사라집니다.")) return;
  lastResultRows = [];
  renderResultTable(lastColumns, lastResultRows);
  resultSection.classList.add("hidden");
});

function renderErrors(errors) {
  errorList.innerHTML = "";
  if (!errors.length) {
    errorSection.classList.add("hidden");
    return;
  }
  errors.forEach((err) => {
    const li = document.createElement("li");
    li.textContent = `${err.filename}: ${err.message}`;
    errorList.appendChild(li);
  });
  errorSection.classList.remove("hidden");
}

extractBtn.addEventListener("click", async () => {
  if (!selectedFiles.length) return;

  statusSection.classList.remove("hidden");
  statusText.textContent = "추출 중입니다... 잠시만 기다려주세요.";
  resultSection.classList.add("hidden");
  errorSection.classList.add("hidden");
  extractBtn.disabled = true;

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files", file));

  try {
    const res = await fetch("/api/extract", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "추출 중 오류가 발생했습니다.");
      return;
    }

    lastColumns = data.columns || lastColumns;
    lastResultRows = lastResultRows.concat(data.rows || []);

    renderErrors(data.errors || []);

    renderResultTable(lastColumns, lastResultRows);
    resultSection.classList.remove("hidden");

    selectedFiles = [];
    renderFileList();
  } catch (err) {
    alert("서버와 통신 중 오류가 발생했습니다: " + err.message);
  } finally {
    statusSection.classList.add("hidden");
    extractBtn.disabled = false;
  }
});

downloadBtn.addEventListener("click", async () => {
  if (!lastResultRows.length) return;

  downloadBtn.disabled = true;
  downloadBtn.textContent = "다운로드 중...";

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: lastResultRows }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert(data.error || "다운로드 중 오류가 발생했습니다.");
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "등기부등본_추출결과.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("다운로드 중 오류가 발생했습니다: " + err.message);
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = "엑셀 다운로드";
  }
});
