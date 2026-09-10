import { describe, expect, it } from 'vitest';
import { evidenceText, gapState, planCategory, directEvidenceText } from './researchDisplay';

describe('ordinary researcher presentation contract', () => {
  it('translates known states and never leaks unknown executor enums', () => {
    expect(gapState('pending_confirmation')).toBe('等待你审阅');
    expect(gapState('internal_executor_v3')).toBe('状态待核实');
    expect(planCategory('baseline')).toBe('建立对照');
  });
  it('preserves original citations without dumping arbitrary object fields', () => {
    expect(evidenceText({ input: 'ImageNet', output: 'segmentation mask', executor: 'secret_internal' })).toBe('输入：ImageNet；输出：segmentation mask');
    expect(evidenceText({ arbitrary_field: 99 })).toBe('暂无可展示的证据，请补充材料');
    expect(directEvidenceText({ title: 'DeepLab', supporting_text: 'We evaluate on Cityscapes.', paper_id: 999 })).toBe('DeepLab：We evaluate on Cityscapes.');
  });
});
