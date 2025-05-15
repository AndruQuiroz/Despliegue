from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["shoppingDB"]

# Encontrar todos los duplicados
duplicate_bids = list(db.bids.aggregate([
    {"$group": {"_id": "$auctionId", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
    {"$match": {"count": {"$gt": 1}}}
]))

# Eliminar duplicados, dejando solo uno
for bid in duplicate_bids:
    print(f"🛑 Eliminando duplicados de auctionId: {bid['_id']}")
    ids_to_delete = bid["ids"][1:]  # Mantener solo uno
    db.bids.delete_many({"_id": {"$in": ids_to_delete}})

print("✅ Se eliminaron los duplicados correctamente.")
