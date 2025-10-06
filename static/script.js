const startCamBtn     = document.getElementById("startCam");
const snapBtn         = document.getElementById("snap");
const chooseFileBtn   = document.getElementById("chooseFile");
const fileInput       = document.getElementById("fileInput");
const cam             = document.getElementById("cam");
const previewImg      = document.getElementById("previewImg");
const sendButton      = document.getElementById("sendButton");
const resultBox       = document.getElementById("resultBox");
const retakeButton    = document.getElementById("retakeButton");
const scanAgainButton = document.getElementById("scanAgainButton");

// Start with history loaded
window.addEventListener("DOMContentLoaded", () => {
  fetch("/api/history")
    .then(r => r.json())
    .then(data => {
      const tbody = document.querySelector("#historyTable tbody");
      data.forEach(e => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${new Date(e.timestamp).toLocaleString()}</td>
          <td>${e.result}</td>
          <td>${e.confidence}%</td>`;
        tbody.appendChild(tr);
      });
    });
});

let cameraStream = null;

// Prevent form submits
document.addEventListener("submit", e => {
  e.preventDefault();
  e.stopPropagation();
});

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    resultBox.textContent = "Camera not supported in this browser or requires HTTPS.";
    console.error("getUserMedia not supported in this context.");
    return;
  }

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
    cam.srcObject = cameraStream;
    cam.classList.remove("hidden");
    previewImg.classList.add("hidden");
    startCamBtn.textContent = "Close Camera";

    cam.onloadedmetadata = async () => {
      try {
        await cam.play();
      } catch (err) {
        console.error("Camera play() failed:", err);
        resultBox.textContent = "Camera started, but playback failed.";
      }
    };
  } catch (err) {
    console.error("Camera error:", err);
    resultBox.textContent = location.hostname !== "localhost"
      ? "Camera blocked (use localhost or HTTPS)."
      : "Cannot access camera (check permissions).";
  }
}

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
  cam.srcObject = null;
  cam.classList.add("hidden");
  previewImg.classList.remove("hidden");
  startCamBtn.textContent = "Open Camera";
}

function loadPreview(file) {
  const reader = new FileReader();
  reader.onload = () => {
    previewImg.src = reader.result;
    previewImg.classList.remove("hidden");
    cam.classList.add("hidden");
    stopCamera();
  };
  reader.readAsDataURL(file);
}

startCamBtn.addEventListener("click", e => {
  e.preventDefault();
  cameraStream ? stopCamera() : startCamera();
});

snapBtn.addEventListener("click", e => {
  e.preventDefault();
  if (!cameraStream) {
    resultBox.textContent = "Camera is not active.";
    return;
  }
  const c = document.createElement("canvas");
  c.width  = cam.videoWidth;
  c.height = cam.videoHeight;
  c.getContext("2d").drawImage(cam, 0, 0);
  c.toBlob(blob => loadPreview(new File([blob], "captured.jpg", { type: "image/jpeg" })), "image/jpeg");
});

chooseFileBtn.addEventListener("click", e => {
  e.preventDefault();
  fileInput.value = "";
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) loadPreview(fileInput.files[0]);
});

retakeButton.addEventListener("click", e => {
  e.preventDefault();
  resultBox.textContent = "No prediction yet";
  previewImg.src = "";
  startCamera();
});

scanAgainButton.addEventListener("click", e => {
  e.preventDefault();
  resultBox.textContent = "No prediction yet";
  previewImg.src = "";
  fileInput.value = "";
  stopCamera();
});

sendButton.addEventListener("click", async () => {
  let file;
  if (fileInput.files.length) {
    file = fileInput.files[0];
  } else if (previewImg.src.startsWith("data:")) {
    const blob = await (await fetch(previewImg.src)).blob();
    file = new File([blob], "captured.jpg", { type: "image/jpeg" });
  } else {
    resultBox.textContent = "No image chosen";
    return;
  }

  const formData = new FormData();
  formData.append("file", file);

  resultBox.textContent = "Processing…";
  sendButton.disabled = true;

  try {
    const res = await fetch(`http://${location.hostname}:5000/api/predict`, {
      method: "POST",
      body: formData
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    resultBox.textContent = `${data.result} — ${data.confidence}%`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${new Date().toLocaleString()}</td>
      <td>${data.result}</td>
      <td>${data.confidence}%</td>`;
    document.querySelector("#historyTable tbody").prepend(tr);

  } catch (err) {
    console.error(err);
    resultBox.textContent = `Error: ${err.message}`;
  } finally {
    sendButton.disabled = false;
  }
});
