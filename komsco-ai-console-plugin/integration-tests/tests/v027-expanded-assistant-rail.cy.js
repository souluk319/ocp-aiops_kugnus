describe('v0.2.7 expanded Assistant rail', () => {
  it('opens the Assistant fullscreen rail with live cluster context and no horizontal overflow', () => {
    const summaryUrl =
      '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/cluster/summary';
    const statusUrl =
      '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status';

    cy.visit('/dashboards/aiops');

    cy.contains('AIOps for OCP / 대시보드', { timeout: 60000 }).should('be.visible');
    cy.contains('api.ocp.cywell.server', { timeout: 60000 }).should('be.visible');

    cy.request(summaryUrl).as('clusterSummary');
    cy.request(statusUrl).as('aiopsStatus');

    cy.get('[aria-label="Open Cywell AI"]', { timeout: 60000 }).click({ force: true });
    cy.get('[aria-label="Cywell AI assistant"]', { timeout: 60000 }).should('be.visible');
    cy.get('[aria-label="Open full screen"]', { timeout: 60000 }).click({ force: true });

    cy.get('.komsco-ai__surface--fullscreen', { timeout: 60000 }).should('be.visible');
    cy.get('@clusterSummary').then(({ body: summary }) => {
      cy.get('@aiopsStatus').then(({ body: status }) => {
        const records = status?.spec?.records || {};
        const actionRecordCount =
          (records.actionProposals?.length || 0) +
          (records.sealedActionPlans?.length || 0) +
          (records.approvalDecisions?.length || 0) +
          (records.executionRecords?.length || 0);
        const diagnosticRecordCount = records.diagnosticRequests?.length || 0;

        cy.get('.komsco-ai__insight-rail', { timeout: 60000 })
          .should('be.visible')
          .within(() => {
            cy.contains('현재 클러스터 컨텍스트').should('be.visible');
            cy.contains(summary.apiUrl || 'api.ocp.cywell.server').should('be.visible');
            cy.contains(String(summary.healthScore)).should('be.visible');
            cy.contains('/ 100').should('be.visible');
            cy.contains(`Node ${summary.nodes.ready}/${summary.nodes.total}`).should('be.visible');
            cy.contains(`${summary.nodes.ready}/${summary.nodes.total} Ready`).should(
              'be.visible',
            );
            cy.contains(
              `Operator ${summary.operators.available}/${summary.operators.total}`,
            ).should('be.visible');
            cy.contains(
              `정상 Operator ${summary.operators.available}/${summary.operators.total}`,
            ).should('be.visible');
            if (summary.nodes.items?.[0]?.name) {
              cy.contains(summary.nodes.items[0].name).should('be.visible');
            }
            if (summary.version?.version) {
              cy.contains(summary.version.version).should('be.visible');
            }
            cy.contains(`최근 진단`).should('be.visible');
            cy.contains(`${diagnosticRecordCount}건`).should('be.visible');
            cy.contains(`승인·실행`).should('be.visible');
            cy.contains(`${actionRecordCount}건`).should('be.visible');
          });
      });
    });

    cy.window().then((win) => {
      const doc = win.document.documentElement;
      const body = win.document.body;
      const surface = win.document.querySelector('.komsco-ai__surface--fullscreen');
      const workspace = win.document.querySelector('.komsco-ai__workspace');
      const rail = win.document.querySelector('.komsco-ai__insight-rail');

      expect(doc.scrollWidth, 'document horizontal overflow').to.be.lte(doc.clientWidth + 1);
      expect(body.scrollWidth, 'body horizontal overflow').to.be.lte(body.clientWidth + 1);
      expect(surface.scrollWidth, 'assistant surface overflow').to.be.lte(surface.clientWidth + 1);
      expect(workspace.scrollWidth, 'assistant workspace overflow').to.be.lte(
        workspace.clientWidth + 1,
      );
      expect(rail.scrollWidth, 'assistant rail overflow').to.be.lte(rail.clientWidth + 1);
    });

    cy.screenshot('v027-expanded-assistant-rail', { capture: 'viewport' });
  });
});
