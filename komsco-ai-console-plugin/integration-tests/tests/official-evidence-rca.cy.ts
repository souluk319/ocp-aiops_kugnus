const OFFICIAL_EVIDENCE_RCA_QUESTION = '어제 새벽에 default namespace Pod가 왜 재시작됐어?';

describe('Ver.0.1.3 official Evidence RCA screen proof', () => {
  it('opens the dashboard and stages the official Evidence RCA question in Cywell AI', () => {
    cy.visit('/dashboards');

    cy.contains('KOMSCO', { timeout: 60000 }).should('be.visible');

    cy.get('body', { timeout: 60000 }).then(($body) => {
      if ($body.find('[aria-label="Open Cywell AI"]').length > 0) {
        cy.get('[aria-label="Open Cywell AI"]').click();
      }
    });

    cy.get('[aria-label="Cywell AI assistant"]', { timeout: 60000 }).should('be.visible');
    cy.get('[aria-label="AIOps 상태 및 실행 모드"]', { timeout: 60000 }).should('be.visible');

    cy.get('[data-assistant-task-mode]', { timeout: 60000 }).then(($button) => {
      if ($button.attr('data-assistant-task-mode') !== 'troubleshooting') {
        cy.wrap($button).click();
        cy.get('[data-komsco-task-mode="troubleshooting"]').click();
      }
    });
    cy.get('[data-assistant-task-mode]').should(
      'have.attr',
      'data-assistant-task-mode',
      'troubleshooting',
    );

    cy.get('textarea[aria-label="Question"]')
      .should('be.visible')
      .clear()
      .type(OFFICIAL_EVIDENCE_RCA_QUESTION, { delay: 0 });
    cy.get('textarea[aria-label="Question"]').should('have.value', OFFICIAL_EVIDENCE_RCA_QUESTION);
    cy.get('button[aria-label="질문 전송"]').should('not.be.disabled');

    cy.screenshot('official-evidence-rca-screen', { capture: 'viewport' });
  });
});
