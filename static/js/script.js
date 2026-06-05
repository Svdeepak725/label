const form = document.getElementById("labelForm");
const loadingOverlay = document.getElementById("loadingOverlay");

function showLoading(message) {
    if (loadingOverlay) {
        loadingOverlay.querySelector("p").textContent = message;
        loadingOverlay.classList.remove("hidden");
    }
}

function hideLoading() {
    if (loadingOverlay) {
        loadingOverlay.classList.add("hidden");
    }
}

function clearErrors() {
    document.querySelectorAll(".error-message").forEach((item) => {
        item.textContent = "";
    });
}

function showErrors(errors) {
    Object.entries(errors || {}).forEach(([key, message]) => {
        const node = document.getElementById(`error-${key}`);
        if (node) {
            node.textContent = message;
        }
    });
}

function getFormData() {
    return {
        groom: document.getElementById("groom")?.value || "",
        bride: document.getElementById("bride")?.value || "",
        date: document.getElementById("date")?.value || "",
        religion: document.getElementById("religion")?.value || "",
        theme: document.getElementById("theme")?.value || "",
    };
}

function updateSamplePreview() {
    const groom = document.getElementById("groom")?.value.trim() || "Groom";
    const bride = document.getElementById("bride")?.value.trim() || "Bride";
    const date = document.getElementById("date")?.value || "10.10.2026";
    const title = document.getElementById("sampleTitle");
    const sampleDate = document.getElementById("sampleDate");
    if (title) {
        title.textContent = `${groom} ❤️ ${bride}`;
    }
    if (sampleDate) {
        sampleDate.textContent = date;
    }
}

async function submitLabelForm(event) {
    event.preventDefault();
    clearErrors();
    const payload = getFormData();
    let hasError = false;

    Object.entries(payload).forEach(([key, value]) => {
        if (!value.trim()) {
            const node = document.getElementById(`error-${key}`);
            if (node) {
                node.textContent = `Please enter your ${key}.`;
            }
            hasError = true;
        }
    });

    if (hasError) {
        return;
    }

    showLoading("Generating your label preview...");

    try {
        const response = await fetch("/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const html = await response.text();
        if (!response.ok) {
            const data = JSON.parse(html || "{}");
            showErrors(data.detail || {});
            return;
        }

        document.open();
        document.write(html);
        document.close();
    } catch (error) {
        console.error(error);
        alert("Something went wrong while generating your label. Please try again.");
    } finally {
        hideLoading();
    }
}

function showToast(message, type = 'success') {
    // Remove any existing toast
    const existingToast = document.getElementById('downloadToast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.id = 'downloadToast';
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <span class="toast-icon">${type === 'success' ? '✓' : '⚠'}</span>
            <p>${message}</p>
            <button type="button" class="toast-close" onclick="this.parentElement.parentElement.remove()">×</button>
        </div>
    `;
    document.body.appendChild(toast);

    // Auto remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 5000);
}

async function downloadAsset(endpoint, filename) {
    // Use the backend to generate the file so downloads work even when browser rendering libraries fail.
    const payload = window.previewData || getFormData();
    showLoading("Preparing your download...");
    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const error = await response.json();
            showErrors(error.errors || error.detail || {});
            showToast('Download failed. Please try again.', 'error');
            return;
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);

        // Show success notification
        const fileType = filename.toLowerCase().endsWith('.pdf') ? 'PDF' : 'PNG';
        showToast(`✅ Download succeeded! ${filename} is ready.`, 'success');

        // read saved filename / public url headers from response
        let publicUrl = response.headers.get('X-Public-URL');
        const saved = response.headers.get('X-Saved-Filename');
        if (!publicUrl) {
            // call save endpoint for this type (png/pdf)
            try {
                const saveEndpoint = endpoint.replace('/download/', '/save/');
                const saveResp = await fetch(saveEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (saveResp.ok) {
                    const j = await saveResp.json();
                    publicUrl = j.url;
                }
            } catch (e) {
                // ignore
            }
        }
    } catch (error) {
        console.error(error);
        showToast("Download failed. Please try again.", 'error');
    } finally {
        hideLoading();
    }
}

function sanitizeName(name) {
    return (name || "").toString().trim().replace(/\s+/g, "_").replace(/[^A-Za-z0-9_\-]/g, "");
}

async function downloadPNG() {
    const data = window.previewData || getFormData();
    const groom = sanitizeName(data.groom) || "groom";
    const bride = sanitizeName(data.bride) || "bride";
    const filename = `${groom}_${bride}_Label.png`;
    
    const pngButton = document.getElementById("downloadPng");
    if (pngButton) {
        pngButton.disabled = true;
        const originalText = pngButton.textContent;
        pngButton.textContent = "Downloading...";
        
        try {
            await downloadAsset("/download/png", filename);
        } finally {
            pngButton.disabled = false;
            pngButton.textContent = originalText;
        }
    } else {
        await downloadAsset("/download/png", filename);
    }
}

async function downloadPDF() {
    const data = window.previewData || getFormData();
    const groom = sanitizeName(data.groom) || "groom";
    const bride = sanitizeName(data.bride) || "bride";
    const filename = `${groom}_${bride}_Label.pdf`;
    
    const pdfButton = document.getElementById("downloadPdf");
    if (pdfButton) {
        pdfButton.disabled = true;
        const originalText = pdfButton.textContent;
        pdfButton.textContent = "Downloading...";
        
        try {
            await downloadAsset("/download/pdf", filename);
        } finally {
            pdfButton.disabled = false;
            pdfButton.textContent = originalText;
        }
    } else {
        await downloadAsset("/download/pdf", filename);
    }
}

function applyPreviewStyles() {
    const card = document.getElementById("labelPreviewCard");
    const colors = window.previewData?.colors;
    if (!card || !colors) {
        return;
    }

    const theme = window.previewData?.theme || '';
    card.style.background = colors.background;
    card.style.borderColor = colors.border;
    card.style.color = colors.text;

    // Theme-specific visual tweaks
    if (theme === 'Royal') {
        card.style.border = `10px solid ${colors.border}`;
        card.style.boxShadow = '0 30px 80px rgba(64, 20, 80, 0.12)';
        card.style.fontFamily = 'Playfair Display, serif';
    } else if (theme === 'Traditional') {
        card.style.border = `8px solid ${colors.border}`;
        card.style.boxShadow = '0 24px 60px rgba(58, 42, 30, 0.12)';
        card.style.fontFamily = 'Playfair Display, serif';
    } else if (theme === 'Modern') {
        card.style.border = `4px solid ${colors.border}`;
        card.style.boxShadow = '0 12px 30px rgba(44, 62, 80, 0.06)';
        card.style.fontFamily = 'Inter, system-ui, sans-serif';
    } else if (theme === 'Minimalist') {
        card.style.border = `1px solid ${colors.border}`;
        card.style.boxShadow = '0 6px 18px rgba(16,16,16,0.06)';
        card.style.fontFamily = 'Inter, system-ui, sans-serif';
    } else {
        card.style.fontFamily = 'Inter, system-ui, sans-serif';
    }
}

function attachPreviewEvents() {
    const pngButton = document.getElementById("downloadPng");
    const pdfButton = document.getElementById("downloadPdf");
    const successToast = document.getElementById("previewSuccess");

    if (successToast) {
        successToast.classList.remove("hidden");
    }

    if (pngButton) {
        pngButton.addEventListener("click", downloadPNG);
    }
    if (pdfButton) {
        pdfButton.addEventListener("click", downloadPDF);
    }
}

function initialize() {
    if (form) {
        form.addEventListener("submit", submitLabelForm);
        ["groom", "bride", "date"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.addEventListener("input", updateSamplePreview);
            }
        });
    }
    updateSamplePreview();
    if (window.previewData) {
        applyPreviewStyles();
        attachPreviewEvents();
    }
}

if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", initialize);
} else {
    initialize();
}
