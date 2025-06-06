document.addEventListener('DOMContentLoaded', function() {
    // --- SEÇÃO 1: CÓDIGO DE CÁLCULO DE TEMPO (MANTENHA ESTE CÓDIGO INALTERADO) ---
    const chegadaInput = document.getElementById('chegada');
    const entregaRoInput = document.getElementById('entrega_ro');
    const saidaInput = document.getElementById('saida');
    const tempoTotalDpInput = document.getElementById('tempo_total_dp');
    const tempoEntregaDpInput = document.getElementById('tempo_entrega_dp');

    function parseTime(timeStr) {
        if (!timeStr) return null;
        const [hours, minutes] = timeStr.split(':').map(Number);
        const date = new Date();
        date.setHours(hours, minutes, 0, 0);
        return date;
    }

    function calculateTimeDifference(start, end) {
        if (!start || !end) return '';
        let diffMs = end.getTime() - start.getTime();
        if (diffMs < 0) { diffMs += 24 * 60 * 60 * 1000; }
        const diffMinutes = Math.floor(diffMs / (1000 * 60));
        const hours = Math.floor(diffMinutes / 60);
        const minutes = diffMinutes % 60;
        const formattedHours = String(hours).padStart(2, '0');
        const formattedMinutes = String(minutes).padStart(2, '0');
        return `${formattedHours}:${formattedMinutes}`;
    }

    function updateTimes() {
        const chegada = parseTime(chegadaInput?.value);
        const entregaRo = parseTime(entregaRoInput?.value);
        const saida = parseTime(saidaInput?.value);

        if (tempoTotalDpInput) {
            tempoTotalDpInput.value = calculateTimeDifference(chegada, saida);
        }
        if (tempoEntregaDpInput) {
            tempoEntregaDpInput.value = calculateTimeDifference(chegada, entregaRo);
        }
    }

    if (chegadaInput) chegadaInput.addEventListener('input', updateTimes);
    if (entregaRoInput) entregaRoInput.addEventListener('input', updateTimes);
    if (saidaInput) saidaInput.addEventListener('input', updateTimes);
    updateTimes();

    // --- SEÇÃO 2: CÓDIGO DA FUNÇÃO DE IMPRESSÃO (NOVO CÓDIGO, FOCADO) ---
    function printSection(sectionId) {
        const printTargetElement = document.getElementById(sectionId);

        // Adiciona classe para o corpo da página para controlar o overflow durante a impressão
        document.body.classList.add('printing-active');

        // Adiciona uma classe ao elemento alvo de impressão
        if (printTargetElement) {
            printTargetElement.classList.add('print-target');
        }

        // Chamar a impressão
        window.print();

        // Restaurar a visibilidade após a impressão
        window.onafterprint = function() {
            // Remove a classe do elemento alvo
            if (printTargetElement) {
                printTargetElement.classList.remove('print-target');
            }
            // Remove a classe do corpo
            document.body.classList.remove('printing-active');
            window.onafterprint = null; // Limpa a função para evitar execuções múltiplas
            window.location.reload(); // Recarrega para garantir que tudo volte ao normal
        };
    }

    // --- Tornar a função printSection global para que possa ser chamada via onclick ---
    window.printSection = printSection;

}); // Fim do DOMContentLoaded