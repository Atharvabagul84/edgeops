"""Thread-safe in-memory stand-in for the DynamoDB calls EdgeOps uses.

Implements GetItem, PutItem, BatchGetItem and TransactWriteItems with the two
condition forms the stores emit. An optional per-call delay models network
round trips so optimistic-concurrency races show up in load tests. Not AWS.
"""
import copy
import threading
import time


class DynamoError(Exception):
    def __init__(self, code, reasons=None):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}
        if reasons is not None:
            self.response["CancellationReasons"] = reasons


class MemoryDynamo:
    def __init__(self, latency_seconds=0.0):
        self.items, self.latency = {}, latency_seconds
        self.lock = threading.Lock()
        self.calls = {}

    @staticmethod
    def _key(key):
        return tuple(sorted((name, value["S"]) for name, value in key.items() if name in ("pk", "sk")))

    def _delay(self, operation):
        with self.lock:
            self.calls[operation] = self.calls.get(operation, 0) + 1
        if self.latency:
            time.sleep(self.latency)

    def _passes(self, request):
        current = self.items.get(self._key(request["Item"]))
        condition = request.get("ConditionExpression")
        if condition is None:
            return True
        if condition == "attribute_not_exists(pk)":
            return current is None
        if condition == "#v = :v":
            expected = request["ExpressionAttributeValues"][":v"]
            return current is not None and current.get(request["ExpressionAttributeNames"]["#v"]) == expected
        raise NotImplementedError(condition)

    def get_item(self, TableName, Key, ConsistentRead=False):
        self._delay("GetItem")
        with self.lock:
            item = self.items.get(self._key(Key))
            return {"Item": copy.deepcopy(item)} if item else {}

    def put_item(self, **request):
        self._delay("PutItem")
        with self.lock:
            if not self._passes(request):
                raise DynamoError("ConditionalCheckFailedException")
            self.items[self._key(request["Item"])] = copy.deepcopy(request["Item"])
        return {}

    def batch_get_item(self, RequestItems):
        self._delay("BatchGetItem")
        responses = {}
        with self.lock:
            for table, request in RequestItems.items():
                found = (self.items.get(self._key(key)) for key in request["Keys"])
                responses[table] = [copy.deepcopy(item) for item in found if item]
        return {"Responses": responses, "UnprocessedKeys": {}}

    def transact_write_items(self, TransactItems):
        self._delay("TransactWriteItems")
        with self.lock:
            requests = [entry["Put"] for entry in TransactItems]
            if len({self._key(request["Item"]) for request in requests}) != len(requests):
                raise DynamoError("ValidationException")
            reasons = [{"Code": "None" if self._passes(request) else "ConditionalCheckFailed"} for request in requests]
            if any(reason["Code"] != "None" for reason in reasons):
                raise DynamoError("TransactionCanceledException", reasons)
            for request in requests:
                self.items[self._key(request["Item"])] = copy.deepcopy(request["Item"])
        return {}

    def keys(self, prefix=""):
        with self.lock:
            return sorted(dict(key)["pk"] + "|" + dict(key).get("sk", "") for key in self.items
                          if dict(key)["pk"].startswith(prefix))
