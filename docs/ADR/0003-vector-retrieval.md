# ADR-0003：确定性 hashing dense vector 作为离线基线

- 状态：Accepted for RC; replaceable

## 比较

- Chroma：易用但增加服务/版本状态；
- LanceDB：本地列式和向量能力强，但新增依赖；
- FAISS：高效但元数据/持久化需另建；
- 确定性 hashing：无网络依赖、测试可复现，但语义能力弱。

## 决策

当前用 SQLite FTS5 + hashing vector 形成可运行混合检索基线。真正 embedding 作为独立可版本化替换项，不允许把当前实现包装成强语义模型。
